"""analyze_security_risk node stub."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.types import RiskTier

NODE_NAME = "analyze_security_risk"


async def run(state: EnterpriseRunState) -> NodePatch:
    tier = RiskTier.high if state.request.extra.get("high_risk") == "1" else RiskTier.low
    return build_patch(
        state,
        NODE_NAME,
        summary=f"analyzed risk tier {tier.value}",
        state_updates={"risk_tier": tier},
    )
