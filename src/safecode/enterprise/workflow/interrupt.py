"""Workflow interrupt primitive for human approval."""

from __future__ import annotations

from safecode.enterprise.approvals.store import ApprovalRequest
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint
from safecode.enterprise.workflow.exceptions import WorkflowInterrupted
from safecode.enterprise.workflow.nodes.registry import WORKFLOW_NODE_ORDER
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.types import WorkflowStatus


def pause_for_approval(
    backend: LocalBackend,
    state: EnterpriseRunState,
    request: ApprovalRequest,
) -> None:
    """Persist approval request and workflow state, then interrupt."""
    backend.approvals.save_request(tenant_id=state.tenant_id, request=request)
    interrupted = state.model_copy(
        update={
            "status": WorkflowStatus.awaiting_approval,
            "awaiting_human_approval": True,
        }
    )
    backend.runs.save_checkpoint(
        tenant_id=interrupted.tenant_id,
        checkpoint=RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=interrupted.run_id,
            completed_nodes=[
                name for name in WORKFLOW_NODE_ORDER if name in interrupted.node_outputs
            ],
            next_node="finalize",
            state=interrupted,
        ),
    )
    raise WorkflowInterrupted(f"awaiting approval for request {request.request_id}")
