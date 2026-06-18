"""plan_actions node stub."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState, Plan, PlanAction
from safecode.enterprise.workflow.types import RiskTier

NODE_NAME = "plan_actions"


async def run(state: EnterpriseRunState) -> NodePatch:
    risk = state.risk_tier or RiskTier.low
    plan_obj = Plan(
        plan_id=f"plan-{state.run_id}",
        summary="deterministic remediation plan",
        actions=[
            PlanAction(
                action_id="action-1",
                title="Review cited policy",
                risk_tier=risk,
                requires_approval=risk in {RiskTier.high, RiskTier.critical},
            )
        ],
    )
    return build_patch(
        state,
        NODE_NAME,
        summary="planned actions",
        state_updates={"plan": plan_obj},
    )
