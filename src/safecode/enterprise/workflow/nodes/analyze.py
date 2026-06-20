"""analyze_security_risk 工作流节点（九步流水线第 4 步）。

- **流水线位置**：第 4 步 / 9 — 基于证据与引用进行安全分析与风险定级。
- **输入**：``findings`` 或 PR/Issue 证据，以及 ``citations``。
- **输出**：``risk_tier``；PR/规划任务额外产出结构化 ``findings``。
- **安全治理**：模型输出仅作分析与定级提案，不具执行权威；结果经 schema 校验后
  写入状态，供计划与审批门引用；无证据时回退到确定性默认定级。
"""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks import pr_review, remediation, secure_planning
from safecode.enterprise.workflow.types import RiskTier

NODE_NAME = "analyze_security_risk"


async def run(state: EnterpriseRunState) -> NodePatch:
    """聚合或分析安全风险，确定 ``risk_tier`` 与可选 ``findings``。"""
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
