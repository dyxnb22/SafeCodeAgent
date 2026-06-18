"""CLI tests for sac enterprise trace export."""

import asyncio
import json
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli_enterprise import enterprise_app
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType


def _run_workflow(tmp_path: Path, run_id: str) -> None:
    sac_root = tmp_path / ".sac"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
    )
    (tmp_path / "fixture.json").write_text("{}", encoding="utf-8")
    asyncio.run(LocalOrchestrator(sac_root, runtime="local").run(state))


def test_trace_export_writes_timeline_json(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_id = "run-export001"
    _run_workflow(tmp_path, run_id)
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        ["trace", "export", run_id, "--root", str(tmp_path)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["run_id"] == run_id
    assert payload["timeline_schema_version"] == 1
    assert (tmp_path / ".sac" / "enterprise" / "runs" / run_id / "timeline.json").is_file()


def test_trace_export_unknown_run_fails_closed(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        ["trace", "export", "run-missing01", "--root", str(tmp_path)],
    )
    assert result.exit_code == 1
