"""approval_gate node stub."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.types import RiskTier, WorkflowStatus

NODE_NAME = "approval_gate"


async def run(state: EnterpriseRunState) -> NodePatch:
    high_risk = state.risk_tier in {RiskTier.high, RiskTier.critical}
    updates: dict = {}
    if high_risk:
        updates["status"] = WorkflowStatus.awaiting_approval
        updates["awaiting_human_approval"] = True
    return build_patch(
        state,
        NODE_NAME,
        summary="approval gate evaluated",
        state_updates=updates,
    )
