"""CLI tests for sac enterprise workflow commands (v1.2.2-T3)."""

import json
import time
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli_enterprise import enterprise_app

_ROOT = Path(__file__).resolve().parents[3]


def test_workflow_run_returns_run_id(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    result = runner.invoke(
        enterprise_app,
        [
            "workflow",
            "run",
            "--task",
            "pr_review",
            "--input",
            str(fixture),
            "--root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["run_id"].startswith("run-")
    assert payload["status"] == "succeeded"


def test_workflow_gc_removes_old_runs(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sac_runs = tmp_path / ".sac" / "enterprise" / "runs" / "run-gc00000001"
    sac_runs.mkdir(parents=True)
    old = time.time() - (8 * 86400)
    import os

    os.utime(sac_runs, (old, old))
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        ["workflow", "gc", "--older-than", "7d", "--root", str(tmp_path)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "run-gc00000001" in payload["removed"]
    assert not sac_runs.exists()
