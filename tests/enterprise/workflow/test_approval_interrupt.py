"""Human-in-the-loop interrupt and resume tests."""

import asyncio
from pathlib import Path

import pytest

from safecode.enterprise.approvals.store import decide_request, load_request
from safecode.enterprise.workflow.checkpoint import load_checkpoint
from safecode.enterprise.workflow.exceptions import WorkflowInterrupted
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus


def _high_risk_state(tmp_path: Path, run_id: str):
    return build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
        extra={"high_risk": "1"},
    )


def test_low_risk_does_not_interrupt(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-lowrisk001",
    )
    final = asyncio.run(orchestrator.run(state))
    assert final.status == WorkflowStatus.succeeded


def test_high_risk_interrupt_persists_request_and_state(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = _high_risk_state(tmp_path, "run-highrisk01")
    with pytest.raises(WorkflowInterrupted):
        asyncio.run(orchestrator.run(state))
    checkpoint = load_checkpoint(sac_root, "run-highrisk01")
    assert checkpoint.state.status == WorkflowStatus.awaiting_approval
    request = load_request(sac_root, "run-highrisk01", "approval-run-highrisk01")
    assert request.status == "pending"


def test_approve_and_resume_completes(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    run_id = "run-approver01"
    with pytest.raises(WorkflowInterrupted):
        asyncio.run(orchestrator.run(_high_risk_state(tmp_path, run_id)))
    decide_request(
        sac_root,
        run_id,
        f"approval-{run_id}",
        decision="approved",
        decision_actor="user:approver",
    )
    final = asyncio.run(orchestrator.resume(run_id))
    assert final.status == WorkflowStatus.succeeded


def test_reject_and_resume_is_terminal_without_finalize_success(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    run_id = "run-rejected01"
    with pytest.raises(WorkflowInterrupted):
        asyncio.run(orchestrator.run(_high_risk_state(tmp_path, run_id)))
    decide_request(
        sac_root,
        run_id,
        f"approval-{run_id}",
        decision="rejected",
        decision_actor="user:approver",
    )
    final = asyncio.run(orchestrator.resume(run_id))
    assert final.status == WorkflowStatus.rejected
    assert final.report is None
