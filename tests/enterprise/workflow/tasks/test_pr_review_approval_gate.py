"""PR review approval gate workflow tests."""

import asyncio
import shutil
from pathlib import Path

import pytest

from safecode.enterprise.approvals.store import approvals_dir, decide_request
from safecode.enterprise.workflow.exceptions import WorkflowInterrupted
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus

_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE = "examples/enterprise/fixtures/pr_sql_injection"


def _cleanup_run(sac_root: Path, run_id: str) -> None:
    run_dir = sac_root / "enterprise" / "runs" / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    approval_dir = approvals_dir(sac_root, run_id)
    if approval_dir.exists():
        shutil.rmtree(approval_dir)


def test_pr_review_live_mode_interrupts_for_approval():
    sac_root = _ROOT / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    run_id = "run-prlive003"
    _cleanup_run(sac_root, run_id)
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref=_FIXTURE,
        actor_id="user:test",
        repo_root=_ROOT,
        run_id=run_id,
    )
    state = state.model_copy(
        update={"request": state.request.model_copy(update={"input_kind": "pr_live"})}
    )
    with pytest.raises(WorkflowInterrupted):
        asyncio.run(orchestrator.run(state))


def test_pr_review_live_resume_records_gated_write():
    sac_root = _ROOT / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    run_id = "run-prlive004"
    _cleanup_run(sac_root, run_id)
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref=_FIXTURE,
        actor_id="user:test",
        repo_root=_ROOT,
        run_id=run_id,
    )
    state = state.model_copy(
        update={"request": state.request.model_copy(update={"input_kind": "pr_live"})}
    )
    with pytest.raises(WorkflowInterrupted):
        asyncio.run(orchestrator.run(state))
    decide_request(
        sac_root,
        run_id,
        f"approval-{run_id}",
        decision="approved",
        decision_actor="user:approver",
    )
    final = asyncio.run(orchestrator.resume(run_id))
    assert final.status == WorkflowStatus.succeeded
    assert any(item.tool_name == "github_write" for item in final.tool_calls)
