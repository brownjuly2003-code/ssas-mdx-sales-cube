"""Offline structure checks of .github/workflows/ssas-windows.yml (nothing is executed here).

The workflow runs only on a GitHub-hosted Windows runner; these tests read its text.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ssas-windows.yml"


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def job(workflow):
    assert list(workflow["jobs"]) == ["ssas"]
    return workflow["jobs"]["ssas"]


def runs(job):
    return [step["run"].replace("\\", "/") for step in job["steps"] if "run" in step]


def test_only_a_manual_start(workflow):
    # YAML 1.1 reads the key "on" as True.
    trigger = workflow.get("on", workflow.get(True))
    assert trigger == {"workflow_dispatch": None}


def test_windows_runner_with_limits(workflow, job):
    assert job["runs-on"] == "windows-2022"
    assert 60 <= job["timeout-minutes"] <= 90
    assert workflow["concurrency"]["cancel-in-progress"] is True
    assert workflow["permissions"] == {"contents": "read"}
    assert job["defaults"]["run"]["shell"] == "powershell"


def test_actions_are_pinned_by_commit(job):
    used = [step["uses"] for step in job["steps"] if "uses" in step]
    assert len(used) == 3
    for action in used:
        assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", action), action


def test_every_run_stops_on_errors_and_checks_native_exit_codes(job):
    for text in runs(job):
        assert "$ErrorActionPreference = 'Stop'" in text or "exit 0" in text, text[:80]
        for line in text.splitlines():
            if (
                re.match(r"\s*(\$\w+ = )?(python|sqlcmd|curl\.exe) ", line)
                and "| Out-Null" not in line
            ):
                assert "$LASTEXITCODE" in text, line


def test_steps_call_the_project_scripts_and_cube_files(job):
    text = "\n".join(runs(job))
    for needed in (
        "scripts/Compare-Cube.ps1",
        "scripts/Confirm-Model.ps1",
        "scripts/Invoke-Xmla.ps1 -Server localhost -InputFile cube/create.xmla",
        "scripts/Invoke-Xmla.ps1 -Server localhost -InputFile cube/process.xmla",
        "scripts/Get-AnalysisServer.ps1",
        "scripts/Test-CubeState.ps1",
        "sql/load.sql",
        "sql/grant_ssas.sql",
        "tests/test_mondrian_answers.py",
    ):
        assert needed in text, needed
        if needed.startswith(("scripts/", "sql/", "tests/")):
            assert (ROOT / needed.split()[0]).is_file(), needed
    assert text.index("cube/create.xmla") < text.index("cube/process.xmla")
    assert text.index("cube/process.xmla") < text.index("scripts/Compare-Cube.ps1")


def test_setup_installs_engine_and_multidimensional_analysis_services(job):
    text = "\n".join(runs(job))
    assert "'/FEATURES=SQLENGINE,AS'" in text
    assert "'/ASSERVERMODE=MULTIDIMENSIONAL'" in text
    assert "/ASSYSADMINACCOUNTS=" in text and "/SQLSYSADMINACCOUNTS=" in text
    assert "Get-FileHash -Algorithm SHA256" in text
    assert re.fullmatch(r"[0-9A-F]{64}", job["env"]["SQL_ISO_SHA256"])
    assert job["env"]["SQL_ISO_URL"].startswith("https://download.microsoft.com/")


def test_evidence_is_uploaded_whatever_the_outcome(job):
    upload = job["steps"][-1]
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["if"] == "always()"
    assert upload["with"]["retention-days"] == 30
    paths = upload["with"]["path"].split()
    assert "reports/ssas/" in paths and "reports/actual/" in paths
    summary = job["steps"][-2]
    assert (
        summary["if"] == "always()"
        and "SSAS answers match the reference" in summary["run"]
    )
    logs = [step for step in job["steps"] if step.get("if") == "failure()"]
    assert len(logs) == 1 and "Setup Bootstrap" not in logs[0]["run"]
    assert "Setup Bootstrap/Log" in job["env"]["SETUP_LOG"].replace("\\", "/")


def test_local_ci_does_not_pick_this_workflow(workflow):
    # The local CI selects workflows by push and pull_request; the Windows job must stay out of it.
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert "push" in ci.get("on", ci.get(True))
    assert set(workflow.get("on", workflow.get(True))).isdisjoint(
        {"push", "pull_request"}
    )
