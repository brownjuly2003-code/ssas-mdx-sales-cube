import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from sales_cube.data import build_star, write_inserts
from sales_cube.reference import reference

ROOT = Path(__file__).resolve().parents[1]
A = {
    "a": "http://schemas.microsoft.com/analysisservices/2003/engine",
    "xs": "http://www.w3.org/2001/XMLSchema",
}
MSPROP = "{urn:schemas-microsoft-com:xml-msprop}"
GRAIN = {
    "Date": ("Day", "DateKey"),
    "Product": ("Product", "ProductKey"),
    "Customer": ("Customer", "CustomerKey"),
}
LEVELS = {
    "Date": ["Year", "Month", "Day"],
    "Product": ["Category", "Product"],
    "Customer": ["Region", "Customer"],
}
# Each damaged copy of the cube definition must be rejected by check_model.
MUTATIONS = {
    "physical column": (
        'msprop:DbColumnName="Revenue"',
        'msprop:DbColumnName="Revenu"',
    ),
    "physical table": (
        'msprop:DbTableName="FactSales"',
        'msprop:DbTableName="FactSale"',
    ),
    "schema": (
        'msprop:DbSchemaName="dbo" msprop:DbTableName="DimDate"',
        'msprop:DbSchemaName="stg" msprop:DbTableName="DimDate"',
    ),
    "lost Year level": (r"<Level>\s*<ID>Year</ID>.*?</Level>", ""),
    "lost Category level": (r"<Level>\s*<ID>Category</ID>.*?</Level>", ""),
    "lost Region level": (r"<Level>\s*<ID>Region</ID>.*?</Level>", ""),
}

# Each SELECT operates on rows loaded from the actual SQL export.
CASES = {
    "01_total": "SELECT SUM(Revenue) FROM sales",
    "02_units_by_year": "SELECT CAST(YearNumber AS TEXT), SUM(Units) FROM sales GROUP BY YearNumber ORDER BY YearNumber",
    "03_category": "SELECT Category, SUM(Revenue) FROM sales WHERE YearNumber=2025 GROUP BY Category ORDER BY Category",
    "04_region": "SELECT Region, SUM(Revenue) FROM sales WHERE YearNumber=2025 GROUP BY Region ORDER BY Region",
    "05_months": "SELECT MonthLabel, SUM(Revenue) FROM sales WHERE YearNumber=2025 GROUP BY MonthLabel ORDER BY MonthLabel",
    "06_ytd_march": "SELECT SUM(Revenue) FROM sales WHERE DayDate BETWEEN '2025-01-01' AND '2025-03-31'",
    "07_prior_march": "SELECT SUM(Revenue) FROM sales WHERE MonthLabel='2024-03'",
    "08_march_change": """SELECT SUM(CASE MonthLabel WHEN '2025-03' THEN Revenue
                        WHEN '2024-03' THEN -Revenue ELSE 0 END) FROM sales""",
    "09_top_products": """SELECT ProductName, SUM(Revenue) FROM sales WHERE YearNumber=2025
                       GROUP BY ProductKey, ProductName ORDER BY SUM(Revenue) DESC, ProductKey LIMIT 3""",
    "10_east_office": """SELECT CustomerName, SUM(Revenue) FROM sales WHERE Category='Office'
                       AND Region='East' AND YearNumber=2025 GROUP BY CustomerName ORDER BY CustomerName""",
}


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    star = build_star(seed=64)
    seed = tmp_path_factory.mktemp("seed") / "seed.sql"
    write_inserts(star, seed)
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys = ON")
    for sql in [(ROOT / "sql/star.sql").read_text(), seed.read_text()]:
        db.executescript(sql.replace("dbo.", ""))
    db.execute("""CREATE VIEW sales AS SELECT * FROM FactSales JOIN DimDate USING (DateKey)
               JOIN DimProduct USING (ProductKey) JOIN DimCustomer USING (CustomerKey)""")
    yield db, reference(star)
    db.close()


@pytest.mark.parametrize("name", CASES)
def test_expected_cellset_against_exported_sql(name, warehouse):
    db, expected = warehouse
    assert [list(row) for row in db.execute(CASES[name])] == expected[name]


@pytest.fixture(scope="module")
def ddl(warehouse):
    db, _ = warehouse
    names = ["DimDate", "DimCustomer", "DimProduct", "FactSales"]
    return {t: {r[1] for r in db.execute(f"PRAGMA table_info({t})")} for t in names}


def check_model(xmla: str, ddl: dict[str, set[str]]) -> None:
    model = ET.fromstring(xmla).find(".//a:Database", A)
    assert model.findtext("a:ID", namespaces=A) == "P64SalesCube"
    dsv = model.find(".//xs:schema/xs:element/xs:complexType/xs:choice", A)
    tables = {}
    for table in dsv:
        name = table.attrib["name"]
        columns = table.findall(".//xs:sequence/xs:element", A)
        # Physical names of the data source view, not only its logical ones.
        assert table.attrib[MSPROP + "DbSchemaName"] == "dbo"
        assert table.attrib[MSPROP + "DbTableName"] == name
        assert all(
            c.attrib[MSPROP + "DbColumnName"] == c.attrib["name"] for c in columns
        )
        tables[name] = {c.attrib["name"] for c in columns}
    assert tables == ddl
    for binding in model.findall(".//a:Source[a:ColumnID]", A):
        assert (
            binding.findtext("a:ColumnID", namespaces=A)
            in tables[binding.findtext("a:TableID", namespaces=A)]
        )
    dims = model.findall("a:Dimensions/a:Dimension", A)
    cube = model.find("a:Cubes/a:Cube", A)
    assert cube.findtext("a:Name", namespaces=A) == "Sales"
    group = cube.find("a:MeasureGroups/a:MeasureGroup", A)
    for dimension in dims:
        name = dimension.findtext("a:ID", namespaces=A)
        key_attr, column = GRAIN[name]
        attrs = {
            attr.findtext("a:ID", namespaces=A): attr
            for attr in dimension.findall("a:Attributes/a:Attribute", A)
        }
        assert attrs[key_attr].findtext("a:Usage", namespaces=A) == "Key"
        levels = [
            node.text for node in dimension.findall(".//a:Level/a:SourceAttributeID", A)
        ]
        assert levels == LEVELS[name]
        assert levels[-1] == key_attr
        for parent, child in zip(levels, levels[1:]):
            assert (
                attrs[child].findtext(
                    ".//a:AttributeRelationship/a:AttributeID", namespaces=A
                )
                == parent
            )
        grain = group.find(
            f"a:Dimensions/a:Dimension[a:CubeDimensionID='{name}']/a:Attributes/a:Attribute",
            A,
        )
        assert grain.findtext("a:Type", namespaces=A) == "Granularity"
        assert grain.findtext("a:AttributeID", namespaces=A) == key_attr
        assert grain.findtext(".//a:ColumnID", namespaces=A) == column
    assert {n.findtext("a:ID", namespaces=A) for n in dims} == set(GRAIN)
    assert {m.text for m in group.findall("a:Measures/a:Measure/a:ID", A)} == {
        "Units",
        "Revenue",
    }
    assert (
        group.findtext(".//a:Partition/a:Source/a:TableID", namespaces=A) == "FactSales"
    )


def test_model_bindings_and_grain(ddl):
    check_model((ROOT / "cube/create.xmla").read_text(encoding="utf-8"), ddl)


@pytest.mark.parametrize("name", MUTATIONS)
def test_damaged_model_is_rejected(name, ddl):
    pattern, replacement = MUTATIONS[name]
    source = (ROOT / "cube/create.xmla").read_text(encoding="utf-8")
    damaged, count = re.subn(pattern, replacement, source, count=1, flags=re.S)
    assert count == 1
    with pytest.raises(AssertionError):
        check_model(damaged, ddl)


def test_every_reference_case_has_a_query_file():
    assert {p.stem for p in (ROOT / "mdx").glob("*.mdx")} == CASES.keys()


def test_regenerate_same_input():
    first, repeat, other = build_star(64), build_star(64), build_star(65)
    assert all(frame.equals(repeat[name]) for name, frame in first.items())
    assert not first["FactSales"].equals(other["FactSales"])
