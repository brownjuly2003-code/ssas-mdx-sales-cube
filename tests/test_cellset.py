from pathlib import Path

import pytest

from sales_cube.cellset import compare, read_cells

DATASET = """<root xmlns="urn:schemas-microsoft-com:xml-analysis:mddataset">
<Axes><Axis name="Axis0"><Tuples><Tuple><Member><Caption>Revenue</Caption></Member></Tuple></Tuples></Axis>
<Axis name="Axis1"><Tuples>
<Tuple><Member><Caption>East</Caption></Member></Tuple>
<Tuple><Member><Caption>West</Caption></Member></Tuple>
</Tuples></Axis></Axes><CellData>
<Cell CellOrdinal="1"><Value>807.00</Value></Cell>
<Cell CellOrdinal="0"><Value>32</Value></Cell>
</CellData></root>"""


def test_caption_order_and_numeric_values():
    assert read_cells(DATASET) == [["East", 32], ["West", 807]]


def test_scalar_in_an_xmla_envelope():
    scalar = """<return><root xmlns="urn:schemas-microsoft-com:xml-analysis:mddataset">
    <Axes><Axis name="Axis0"><Tuples><Tuple><Member><Caption>Revenue</Caption></Member></Tuple>
    </Tuples></Axis><Axis name="SlicerAxis"><Tuples><Tuple /></Tuples></Axis></Axes>
    <CellData><Cell CellOrdinal="0"><Value>0</Value></Cell></CellData></root></return>"""
    assert read_cells(scalar) == [[0]]


@pytest.mark.parametrize(
    "bad",
    [
        DATASET.replace('CellOrdinal="1"', 'CellOrdinal="0"'),
        DATASET.replace("807.00", "807.25"),
        DATASET.replace('<Cell CellOrdinal="0"><Value>32</Value></Cell>', ""),
        "<root><Messages><Error Description='MDX failed' /></Messages></root>",
    ],
)
def test_invalid_cellset_fails(bad):
    with pytest.raises(ValueError):
        read_cells(bad)


@pytest.fixture
def run_folders(tmp_path):
    answers, queries = tmp_path / "actual", tmp_path / "mdx"
    answers.mkdir()
    queries.mkdir()
    for name in ("01_region", "02_region"):
        (answers / f"{name}.xml").write_text(DATASET, encoding="utf-8")
        (queries / f"{name}.mdx").write_text("SELECT", encoding="utf-8")
    rows = [["East", 32], ["West", 807]]
    return {"01_region": rows, "02_region": rows}, answers, queries


def test_compare_accepts_the_exact_set_of_queries_and_answers(run_folders):
    expected, answers, queries = run_folders
    assert compare(expected, answers, queries) == 2


def test_compare_rejects_a_stale_answer_of_a_removed_query(run_folders):
    expected, answers, queries = run_folders
    (queries / "02_region.mdx").unlink()
    with pytest.raises(ValueError, match="query files differ"):
        compare(expected, answers, queries)


def test_compare_rejects_missing_and_extra_answers(run_folders):
    expected, answers, queries = run_folders
    (answers / "03_old.xml").write_text(DATASET, encoding="utf-8")
    with pytest.raises(ValueError, match="answer files differ.*03_old"):
        compare(expected, answers, queries)
    (answers / "03_old.xml").unlink()
    (answers / "02_region.xml").unlink()
    with pytest.raises(ValueError, match="answer files differ.*02_region"):
        compare(expected, answers, queries)


def test_compare_reports_a_different_cell(run_folders):
    expected, answers, queries = run_folders
    expected["02_region"] = [["East", 32], ["West", 808]]
    with pytest.raises(ValueError, match="02_region: expected"):
        compare(expected, answers, queries)


def test_compare_script_uses_a_new_folder_and_passes_the_queries():
    # Text check only: the script needs Analysis Services and has never been run.
    script = Path(__file__).resolve().parents[1] / "scripts/Compare-Cube.ps1"
    text = script.read_text(encoding="utf-8")
    assert "Get-Date -Format" in text and "already exists" in text
    assert "--queries $queries" in text
