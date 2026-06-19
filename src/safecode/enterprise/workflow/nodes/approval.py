"""approval_gate node."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks import pr_review, remediation
from safecode.enterprise.workflow.types import RiskTier, WorkflowStatus

NODE_NAME = "approval_gate"


async def run(state: EnterpriseRunState) -> NodePatch:
    if state.validation_failed:
        return build_patch(
            state,
            NODE_NAME,
            summary="approval blocked by failed validation",
            state_updates={
                "status": WorkflowStatus.blocked,
                "awaiting_human_approval": False,
            },
            status="blocked",
        )
    high_risk = state.risk_tier in {RiskTier.high, RiskTier.critical}
    live_post = pr_review.is_pr_review_task(state) and state.request.input_kind == "pr_live"
    patch_apply = remediation.is_remediation_task(state) and any(
        item.kind == "patch" for item in state.proposals
    )
    needs_approval = high_risk or live_post or patch_apply
    updates: dict = {}
    if needs_approval:
        updates["status"] = WorkflowStatus.awaiting_approval
        updates["awaiting_human_approval"] = True
    return build_patch(
        state,
        NODE_NAME,
        summary="approval gate evaluated",
        state_updates=updates,
    )
