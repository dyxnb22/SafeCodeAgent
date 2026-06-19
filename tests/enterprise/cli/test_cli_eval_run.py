"""CLI tests for sac enterprise eval commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli_enterprise import enterprise_app

_ROOT = Path(__file__).resolve().parents[3]


def test_eval_run_all_writes_dashboard(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(_ROOT)
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        ["eval", "run", "--suite", "smoke", "--root", str(_ROOT)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert Path(payload["dashboard"]).is_file()


def test_eval_dashboard_prints_markdown(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(_ROOT)
    runner = CliRunner()
    runner.invoke(enterprise_app, ["eval", "run", "--suite", "smoke", "--root", str(_ROOT)])
    result = runner.invoke(enterprise_app, ["eval", "dashboard", "--root", str(_ROOT)])
    assert result.exit_code == 0
    assert "# Enterprise Evaluation Dashboard" in result.stdout
