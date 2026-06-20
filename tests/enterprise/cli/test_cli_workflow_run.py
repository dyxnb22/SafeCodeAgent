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
    import os

    monkeypatch.chdir(tmp_path)
    sac_root = tmp_path / ".sac"
    run_id = "run-gc00000001"
    from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint, save_checkpoint
    from safecode.enterprise.workflow.orchestrator import build_initial_state
    from safecode.enterprise.workflow.types import TaskType

    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
        tenant_id="local",
    )
    save_checkpoint(
        sac_root,
        RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=run_id,
            completed_nodes=[],
            next_node="classify_request",
            state=state,
        ),
    )
    sac_runs = sac_root / "enterprise" / "runs" / run_id
    old = time.time() - (8 * 86400)
    os.utime(sac_runs, (old, old))
    os.utime(sac_runs / "state.json", (old, old))
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        ["workflow", "gc", "--older-than", "7d", "--root", str(tmp_path)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert run_id in payload["removed"]
    assert not sac_runs.exists()
