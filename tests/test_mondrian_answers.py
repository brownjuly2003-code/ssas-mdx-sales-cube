"""The answers an engine gave on the stand, and negative controls on them.

By default the answers of Mondrian: the CI job with SQL Server runs this file after
mondrian/RunMdx.java has written reports/mondrian/answers. The Windows workflow
.github/workflows/ssas-windows.yml points P64_ANSWERS at the folder of SSAS answers
written by scripts/Compare-Cube.ps1, and the same checks run on them (the test names
keep "mondrian" because the protocols in docs/runs cite them).
"""

import copy
import json
import os
import shutil
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

import pytest

from sales_cube.cellset import NS, compare

pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parents[1]
ANSWERS = ROOT / os.environ.get("P64_ANSWERS", "reports/mondrian/answers")
QUERIES = ROOT / "mdx"
EXPECTED = json.loads((ROOT / "docs/runs/expected-seed64.json").read_text("utf-8"))


@pytest.fixture
def answers(tmp_path):
    copied = tmp_path / "answers"
    shutil.copytree(ANSWERS, copied)
    return copied


def test_ten_mondrian_answers_match_the_reference():
    assert len(EXPECTED) == 10
    assert compare(EXPECTED, ANSWERS, QUERIES) == 10


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_a_changed_reference_value_fails(name):
    damaged = copy.deepcopy(EXPECTED)
    damaged[name][0][-1] += 1
    with pytest.raises(ValueError, match=f"{name}: expected"):
        compare(damaged, ANSWERS, QUERIES)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_a_changed_mondrian_value_fails(name, answers):
    path = answers / f"{name}.xml"
    tree = ET.parse(path)
    value = tree.getroot().find(".//m:CellData/m:Cell/m:Value", NS)
    value.text = str(Decimal(value.text) + 1)
    tree.write(path, encoding="utf-8")
    with pytest.raises(ValueError, match=f"{name}: expected"):
        compare(EXPECTED, answers, QUERIES)


def test_swapped_captions_fail(answers):
    path = answers / "09_top_products.xml"
    tree = ET.parse(path)
    captions = tree.getroot().findall(
        ".//m:Axis[@name='Axis1']/m:Tuples/m:Tuple/m:Member/m:Caption", NS
    )
    captions[0].text, captions[1].text = captions[1].text, captions[0].text
    tree.write(path, encoding="utf-8")
    with pytest.raises(ValueError, match="09_top_products: expected"):
        compare(EXPECTED, answers, QUERIES)


def test_a_missing_answer_fails(answers):
    (answers / "10_east_office.xml").unlink()
    with pytest.raises(ValueError, match="answer files differ.*10_east_office"):
        compare(EXPECTED, answers, QUERIES)
