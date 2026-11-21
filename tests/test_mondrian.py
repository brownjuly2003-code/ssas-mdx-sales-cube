"""Offline checks of the Mondrian side: schema against cube/create.xmla, statements, report."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from sales_cube import mondrian

ROOT = Path(__file__).resolve().parents[1]
A = {"a": "http://schemas.microsoft.com/analysisservices/2003/engine"}
LEVEL_TYPES = {"Years": "TimeYears", "Months": "TimeMonths", "Days": "TimeDays"}


def ssas_model(xmla: str) -> dict:
    """Tables, key and name columns, level order and measures of the SSAS definition."""
    database = ET.fromstring(xmla).find(".//a:Database", A)
    cube = database.find("a:Cubes/a:Cube", A)
    group = cube.find("a:MeasureGroups/a:MeasureGroup", A)

    def column(node, path):
        found = node.find(path, A)
        if found is None:
            return None
        return (
            found.findtext("a:TableID", namespaces=A),
            found.findtext("a:ColumnID", namespaces=A),
        )

    dimensions = {}
    for dimension in database.findall("a:Dimensions/a:Dimension", A):
        name = dimension.findtext("a:Name", namespaces=A)
        attrs = {
            a.findtext("a:ID", namespaces=A): a
            for a in dimension.findall("a:Attributes/a:Attribute", A)
        }
        hierarchy = dimension.find("a:Hierarchies/a:Hierarchy", A)
        levels = []
        for level in hierarchy.findall("a:Levels/a:Level", A):
            attr = attrs[level.findtext("a:SourceAttributeID", namespaces=A)]
            levels.append(
                (
                    level.findtext("a:Name", namespaces=A),
                    column(attr, "a:KeyColumns/a:KeyColumn/a:Source"),
                    column(attr, "a:NameColumn/a:Source"),
                    LEVEL_TYPES.get(attr.findtext("a:Type", namespaces=A)),
                )
            )
        grain = group.find(
            f"a:Dimensions/a:Dimension[a:CubeDimensionID='{name}']//a:Source", A
        )
        dimensions[name] = {
            "time": dimension.findtext("a:Type", namespaces=A) == "Time",
            "hierarchy": hierarchy.findtext("a:Name", namespaces=A),
            "foreign key": grain.findtext("a:ColumnID", namespaces=A),
            "levels": levels,
        }
    measures = {
        m.findtext("a:Name", namespaces=A): (
            column(m, "a:Source/a:Source"),
            m.findtext("a:AggregateFunction", namespaces=A).lower(),
        )
        for m in group.findall("a:Measures/a:Measure", A)
    }
    return {
        "cube": cube.findtext("a:Name", namespaces=A),
        "fact": group.findtext(".//a:Partition/a:Source/a:TableID", namespaces=A),
        "dimensions": dimensions,
        "measures": measures,
    }


def mondrian_model(schema: str) -> dict:
    """The same description read from the Mondrian schema."""
    cube = ET.fromstring(schema).find("Cube")
    fact = cube.find("Table")
    assert fact.get("schema") == "dbo"
    dimensions = {}
    for dimension in cube.findall("Dimension"):
        hierarchies = dimension.findall("Hierarchy")
        assert len(hierarchies) == 1
        hierarchy = hierarchies[0]
        table = hierarchy.find("Table")
        assert table.get("schema") == "dbo"
        name = table.get("name")
        levels = [
            (
                level.get("name"),
                (name, level.get("column")),
                (name, level.get("nameColumn")) if level.get("nameColumn") else None,
                level.get("levelType"),
            )
            for level in hierarchy.findall("Level")
        ]
        # The lowest level is the key of the dimension table and the grain of the fact.
        assert levels[-1][1] == (name, hierarchy.get("primaryKey"))
        assert hierarchy.get("primaryKey") == dimension.get("foreignKey")
        dimensions[dimension.get("name")] = {
            "time": dimension.get("type") == "TimeDimension",
            "hierarchy": hierarchy.get("name"),
            "foreign key": dimension.get("foreignKey"),
            "levels": levels,
        }
    measures = {
        m.get("name"): ((fact.get("name"), m.get("column")), m.get("aggregator"))
        for m in cube.findall("Measure")
    }
    return {
        "cube": cube.get("name"),
        "fact": fact.get("name"),
        "dimensions": dimensions,
        "measures": measures,
    }


def check_schema(schema: str, xmla: str) -> None:
    assert mondrian_model(schema) == ssas_model(xmla)


XMLA = (ROOT / "cube/create.xmla").read_text(encoding="utf-8")
SCHEMA = (ROOT / "cube/mondrian.xml").read_text(encoding="utf-8")
# Each damaged copy of the Mondrian schema must be rejected by check_schema.
MUTATIONS = {
    "key column": ('column="MonthKey"', 'column="DateKey"'),
    "name column": ('nameColumn="ProductName"', 'nameColumn="Category"'),
    "table": ('name="DimCustomer"', 'name="DimClient"'),
    "foreign key": ('foreignKey="ProductKey"', 'foreignKey="LineKey"'),
    "level order": (
        r'(<Level name="Year"[^>]*/>)(\s*)(<Level name="Month"[^>]*/>)',
        r"\3\2\1",
    ),
    "level type": ('levelType="TimeMonths"', 'levelType="TimeDays"'),
    "lost measure": (r'<Measure name="Units"[^>]*/>', ""),
    "aggregator": ('aggregator="sum"', 'aggregator="max"'),
    "hierarchy": ('name="Geography"', 'name="Regions"'),
    "fact table": ('name="FactSales"', 'name="DimDate"'),
}


def test_mondrian_schema_matches_the_ssas_definition():
    check_schema(SCHEMA, XMLA)
    model = mondrian_model(SCHEMA)
    assert [level[0] for level in model["dimensions"]["Date"]["levels"]] == [
        "Year",
        "Month",
        "Day",
    ]
    assert set(model["measures"]) == {"Units", "Revenue"}


@pytest.mark.parametrize("name", MUTATIONS)
def test_damaged_mondrian_schema_is_rejected(name):
    pattern, replacement = MUTATIONS[name]
    damaged, count = re.subn(pattern, replacement, SCHEMA, count=1)
    assert count == 1
    with pytest.raises(AssertionError):
        check_schema(damaged, XMLA)


def test_statements_keep_the_queries_except_listed_adaptations(tmp_path):
    output = tmp_path / "statements"
    changed, terminators = mondrian.write_statements(ROOT / "mdx", output)
    assert changed == sorted(mondrian.ADAPTATIONS) == ["09_top_products"]
    assert terminators == 10
    queries = sorted(path.stem for path in (ROOT / "mdx").glob("*.mdx"))
    assert sorted(path.stem for path in output.glob("*.mdx")) == queries
    assert len(queries) == 10
    for name in queries:
        text = (ROOT / "mdx" / f"{name}.mdx").read_text(encoding="utf-8")
        original = text.rstrip().removesuffix(";") + "\n"
        assert ";" not in original
        statement = (output / f"{name}.mdx").read_text(encoding="utf-8")
        if name in mondrian.ADAPTATIONS:
            assert statement != original
            for old, new, _ in mondrian.ADAPTATIONS[name]:
                assert old in original and new in statement
        else:
            assert statement == original


def test_the_only_adaptation_drops_typed_and_keeps_the_key_tie_break(tmp_path):
    mondrian.write_statements(ROOT / "mdx", tmp_path / "statements")
    ssas = (ROOT / "mdx/09_top_products.mdx").read_text(encoding="utf-8")
    adapted = (tmp_path / "statements/09_top_products.mdx").read_text(encoding="utf-8")
    assert adapted == ssas.rstrip().removesuffix(";").replace(", TYPED)", ")") + "\n"
    # KEY0 is the product key in SSAS; the Mondrian schema declares it on the same column.
    level = ET.fromstring(SCHEMA).find(".//Level[@name='Product']")
    keys = [(p.get("name"), p.get("column"), p.get("type")) for p in level]
    assert keys == [("KEY0", level.get("column"), "Numeric")]
    assert level.get("column") == "ProductKey"


def test_statements_go_to_a_new_folder(tmp_path):
    mondrian.write_statements(ROOT / "mdx", tmp_path / "statements")
    with pytest.raises(FileExistsError):
        mondrian.write_statements(ROOT / "mdx", tmp_path / "statements")


def test_only_the_final_terminator_is_dropped():
    assert mondrian.strip_terminator("SELECT 1;\n") == "SELECT 1\n"
    assert mondrian.strip_terminator("SELECT 1 ; \n\n") == "SELECT 1\n"
    assert mondrian.strip_terminator("SELECT 1\n") == "SELECT 1\n"
    assert mondrian.strip_terminator("SELECT ';' ;") == "SELECT ';'\n"


def test_an_adaptation_must_match_exactly_once(monkeypatch):
    monkeypatch.setitem(mondrian.ADAPTATIONS, "01_total", [("[Sales]", "[X]", "test")])
    assert mondrian.adapt("01_total", "FROM [Sales]") == "FROM [X]"
    with pytest.raises(ValueError, match="one occurrence"):
        mondrian.adapt("01_total", "FROM [Sales] JOIN [Sales]")
    with pytest.raises(ValueError, match="one occurrence"):
        mondrian.adapt("01_total", "FROM [Cube]")


CELLSET = """<root xmlns="urn:schemas-microsoft-com:xml-analysis:mddataset">
<Axes><Axis name="Axis0"><Tuples><Tuple><Member><Caption>Revenue</Caption></Member></Tuple></Tuples></Axis>
</Axes><CellData><Cell CellOrdinal="0"><Value>{value}</Value></Cell></CellData></root>"""


def test_report_marks_matches_and_mismatches(tmp_path):
    (tmp_path / "01_total.xml").write_text(CELLSET.format(value="870055"), "utf-8")
    (tmp_path / "07_prior_march.xml").write_text(CELLSET.format(value="1"), "utf-8")
    expected = {
        "01_total": [[870055]],
        "07_prior_march": [[42395]],
        "10_east_office": [["Aspen", 48335]],
    }
    lines = mondrian.report(expected, tmp_path)
    assert lines[0].endswith("match yes")
    assert lines[1].endswith("match NO")
    assert "error" in lines[2] and lines[2].endswith("match NO")
    assert lines[-1] == "1/3 Mondrian answers match the reference"


def test_report_names_the_answering_engine(tmp_path):
    (tmp_path / "01_total.xml").write_text(CELLSET.format(value="870055"), "utf-8")
    lines = mondrian.report({"01_total": [[870055]]}, tmp_path, engine="SSAS")
    assert lines == [
        "01_total | expected [[870055]] | SSAS [[870055]] | match yes",
        "1/1 SSAS answers match the reference",
    ]


def test_every_downloaded_jar_is_pinned_by_sha256():
    lines = (ROOT / "mondrian/artifacts.txt").read_text(encoding="utf-8").splitlines()
    rows = [line.split() for line in lines if line.strip()]
    assert len(rows) == 14
    for digest, name, url in rows:
        assert re.fullmatch(r"[0-9a-f]{64}", digest), name
        assert url.startswith("https://") and url.endswith("/" + name), name
        assert re.search(r"\d", name) and "SNAPSHOT" not in url, name
    assert any(name == "mondrian-3.2.0-13661-JS-3.jar" for _, name, _ in rows)
    script = (ROOT / "scripts/fetch-mondrian.sh").read_text(encoding="utf-8")
    assert "sha256sum -c" in script and "set -euo pipefail" in script
