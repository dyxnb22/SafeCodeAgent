"""CLI tests for sac enterprise approval commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli_enterprise import enterprise_app


def _start_high_risk_run(tmp_path: Path) -> str:
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
        env={"WORKFLOW_RUNTIME": "local"},
    )
    assert result.exit_code in {0, 3}
    return json.loads(result.stdout)["run_id"]


def test_approval_list_show_approve_resume(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    sac_root = tmp_path / ".sac"
    orchestrator_state_dir = sac_root / "enterprise" / "runs"
    orchestrator_state_dir.mkdir(parents=True, exist_ok=True)

    from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
    from safecode.enterprise.workflow.types import TaskType
    import asyncio

    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-cliapprove1",
        extra={"high_risk": "1"},
    )
    (tmp_path / "fixture.json").write_text("{}", encoding="utf-8")
    try:
        asyncio.run(LocalOrchestrator(sac_root, runtime="local").run(state))
    except Exception:
        pass

    list_result = runner.invoke(
        enterprise_app,
        ["approval", "list", "run-cliapprove1", "--root", str(tmp_path)],
    )
    assert list_result.exit_code == 0
    items = json.loads(list_result.stdout)
    assert len(items) == 1
    request_id = items[0]["request_id"]

    show_result = runner.invoke(
        enterprise_app,
        ["approval", "show", "run-cliapprove1", request_id, "--root", str(tmp_path)],
    )
    assert show_result.exit_code == 0

    approve_result = runner.invoke(
        enterprise_app,
        [
            "approval",
            "approve",
            "run-cliapprove1",
            request_id,
            "--actor",
            "user:approver",
            "--root",
            str(tmp_path),
        ],
    )
    assert approve_result.exit_code == 0

    second = runner.invoke(
        enterprise_app,
        [
            "approval",
            "approve",
            "run-cliapprove1",
            request_id,
            "--actor",
            "user:approver",
            "--root",
            str(tmp_path),
        ],
    )
    assert second.exit_code == 1

    resume_result = runner.invoke(
        enterprise_app,
        ["workflow", "resume", "run-cliapprove1", "--root", str(tmp_path)],
    )
    assert resume_result.exit_code == 0
    assert json.loads(resume_result.stdout)["status"] == "succeeded"
