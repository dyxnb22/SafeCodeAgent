"""CLI tests for sac enterprise trace show."""

import asyncio
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli_enterprise import enterprise_app
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType


def test_trace_show_prints_markdown(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_id = "run-show00001"
    (tmp_path / "fixture.json").write_text("{}", encoding="utf-8")
    sac_root = tmp_path / ".sac"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
    )
    asyncio.run(LocalOrchestrator(sac_root, runtime="local").run(state))
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        ["trace", "show", run_id, "--root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "# Enterprise Run Dashboard" in result.stdout
    assert "## Timeline" in result.stdout


def test_trace_show_unknown_run_fails_closed(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        ["trace", "show", "run-missing02", "--root", str(tmp_path)],
    )
    assert result.exit_code == 1
