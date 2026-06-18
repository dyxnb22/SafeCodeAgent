"""Workflow interrupt primitive for human approval."""

from __future__ import annotations

from pathlib import Path

from safecode.enterprise.approvals.store import ApprovalRequest, save_request
from safecode.enterprise.workflow.checkpoint import (
    CHECKPOINT_SCHEMA_VERSION,
    RunCheckpoint,
    save_checkpoint,
)
from safecode.enterprise.workflow.exceptions import WorkflowInterrupted
from safecode.enterprise.workflow.nodes.registry import WORKFLOW_NODE_ORDER
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.types import WorkflowStatus


def pause_for_approval(
    sac_root: Path,
    state: EnterpriseRunState,
    request: ApprovalRequest,
) -> None:
    """Persist approval request and workflow state, then interrupt."""
    save_request(sac_root, request)
    interrupted = state.model_copy(
        update={
            "status": WorkflowStatus.awaiting_approval,
            "awaiting_human_approval": True,
        }
    )
    save_checkpoint(
        sac_root,
        RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=interrupted.run_id,
            completed_nodes=[name for name in WORKFLOW_NODE_ORDER if name in interrupted.node_outputs],
            next_node="finalize",
            state=interrupted,
        ),
    )
    raise WorkflowInterrupted(f"awaiting approval for request {request.request_id}")
