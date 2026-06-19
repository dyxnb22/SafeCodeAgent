"""analyze_security_risk node."""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks import pr_review, remediation, secure_planning
from safecode.enterprise.workflow.types import RiskTier

NODE_NAME = "analyze_security_risk"


async def run(state: EnterpriseRunState) -> NodePatch:
    if remediation.is_remediation_task(state) and state.findings:
        tier = remediation.aggregate_risk_tier(state.findings)
        return build_patch(
            state,
            NODE_NAME,
            summary=f"analyzed risk tier {tier.value}",
            state_updates={"risk_tier": tier},
        )
    if pr_review.is_pr_review_task(state) and state.pull_request_evidence is not None:
        findings, tier = pr_review.analyze_pr_security(
            state.pull_request_evidence,
            state.citations,
        )
        return build_patch(
            state,
            NODE_NAME,
            summary=f"analyzed risk tier {tier.value}",
            state_updates={"risk_tier": tier, "findings": findings},
        )
    if secure_planning.is_secure_planning_task(state) and state.issue_evidence is not None:
        findings, tier = secure_planning.analyze_ticket_security(
            state.issue_evidence,
            state.citations,
        )
        return build_patch(
            state,
            NODE_NAME,
            summary=f"analyzed risk tier {tier.value}",
            state_updates={"risk_tier": tier, "findings": findings},
        )
    tier = RiskTier.high if state.request.extra.get("high_risk") == "1" else RiskTier.low
    return build_patch(
        state,
        NODE_NAME,
        summary=f"analyzed risk tier {tier.value}",
        state_updates={"risk_tier": tier},
    )
