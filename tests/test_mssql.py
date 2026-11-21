"""Load the published seed with sqlcmd and read the star back from SQL Server."""

import subprocess

import pytest

from sales_cube.data import build_star

pytestmark = pytest.mark.slow

# varchar columns of the star: sqlcmd -W trims their trailing spaces in the printed value.
TEXT_COLUMNS = {
    "DimDate": ["MonthLabel"],
    "DimProduct": ["ProductName", "Category"],
    "DimCustomer": ["CustomerName", "Region"],
    "FactSales": [],
}


def sqlcmd(database, *args, check=True):
    return subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "mssql",
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "tcp:localhost,1433",
            "-C",
            "-U",
            "sa",
            "-b",
            "-r",
            "1",
            "-h",
            "-1",
            "-W",
            "-s",
            "|",
            "-d",
            database,
            *args,
        ],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=check,
    )


@pytest.fixture(scope="module")
def warehouse():
    sqlcmd("master", "-Q", "CREATE DATABASE P64SalesDW")
    sqlcmd("P64SalesDW", "-i", "sql/load.sql")
    return build_star(seed=64)


def read_rows(database, query):
    result = sqlcmd(database, "-Q", "SET NOCOUNT ON; " + query)
    return [line.split("|") for line in result.stdout.splitlines() if line.strip()]


def assert_table_matches(table, frame):
    key = frame.columns[0]
    columns = ", ".join(frame.columns)
    actual = read_rows(
        "P64SalesDW", f"SELECT {columns} FROM dbo.{table} ORDER BY {key}"
    )
    expected = [list(map(str, row)) for row in frame.itertuples(index=False, name=None)]
    assert actual == expected
    text = TEXT_COLUMNS[table]
    if text:
        lengths = ", ".join(f"DATALENGTH({column})" for column in text)
        stored = read_rows(
            "P64SalesDW", f"SELECT {key}, {lengths} FROM dbo.{table} ORDER BY {key}"
        )
        source = frame[[key, *text]].itertuples(index=False, name=None)
        assert stored == [
            [str(row[0]), *(str(len(value.encode("ascii"))) for value in row[1:])]
            for row in source
        ]


def test_text_columns_cover_every_character_column_of_the_star(warehouse):
    query = (
        "SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE DATA_TYPE IN ('char', 'varchar', 'nchar', 'nvarchar') ORDER BY TABLE_NAME, ORDINAL_POSITION"
    )
    declared = {}
    for table, column in read_rows("P64SalesDW", query):
        declared.setdefault(table, []).append(column)
    assert declared == {
        table: columns for table, columns in TEXT_COLUMNS.items() if columns
    }


def test_trailing_space_in_the_printed_value_and_in_the_length():
    # Measured on the stand: sqlcmd -W keeps a value's own trailing space, in the middle of a row and at its end.
    query = "DECLARE @t TABLE (v varchar(32)); INSERT @t VALUES ('Desk '); SELECT v, DATALENGTH(v), v FROM @t"
    assert read_rows("master", query) == [["Desk ", "5", "Desk "]]


@pytest.mark.parametrize("table", ["DimDate", "DimProduct", "DimCustomer", "FactSales"])
def test_loaded_rows(warehouse, table):
    assert_table_matches(table, warehouse[table])


def test_repeat_load_preserves_existing_star(warehouse):
    result = sqlcmd("P64SalesDW", "-i", "sql/load.sql", check=False)
    assert result.returncode != 0
    assert "2714" in result.stderr, result.stderr
    for table, frame in warehouse.items():
        assert_table_matches(table, frame)


def test_load_rejects_another_database():
    sqlcmd("master", "-Q", "CREATE DATABASE P64WrongTarget")
    result = sqlcmd("P64WrongTarget", "-i", "sql/load.sql", check=False)
    assert result.returncode != 0
    assert "Select the dedicated P64SalesDW database." in result.stderr, result.stderr
    result = sqlcmd(
        "P64WrongTarget", "-Q", "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.tables"
    )
    assert result.stdout.strip() == "0"
