"""plan_actions 工作流节点（九步流水线第 5 步）。

- **流水线位置**：第 5 步 / 9 — 生成带风险排序与审批要求的行动 ``Plan``。
- **输入**：``findings``、``citations``、``risk_tier`` 及任务专属证据。
- **输出**：结构化 ``plan``（``PlanAction`` 列表，含 ``requires_approval`` 标记）。
- **安全治理**：计划为模型或确定性规则的提案，不触发工具执行；高风险动作在计划中
  显式标记需人工审批，供 ``approval_gate`` 与 ``finalize`` 消费。
"""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState, Plan, PlanAction
from safecode.enterprise.workflow.tasks import pr_review, remediation, secure_planning
from safecode.enterprise.workflow.types import RiskTier

NODE_NAME = "plan_actions"


async def run(state: EnterpriseRunState) -> NodePatch:
    """按任务类型构建修复、PR 审查或安全实施计划。"""
    if remediation.is_remediation_task(state) and state.findings:
        plan_obj = remediation.build_remediation_plan(state, state.findings, state.citations)
        return build_patch(
            state,
            NODE_NAME,
            summary="planned remediation actions",
            state_updates={"plan": plan_obj},
        )
    if pr_review.is_pr_review_task(state):
        plan_obj = pr_review.build_pr_plan(
            state,
            state.findings,
            state.risk_tier or RiskTier.low,
        )
        return build_patch(
            state,
            NODE_NAME,
            summary="planned actions",
            state_updates={"plan": plan_obj},
        )
    if secure_planning.is_secure_planning_task(state) and state.issue_evidence is not None:
        plan_obj = secure_planning.build_planning_plan(
            state,
            state.issue_evidence,
            state.citations,
            state.findings,
            state.risk_tier or RiskTier.medium,
        )
        return build_patch(
            state,
            NODE_NAME,
            summary="planned secure implementation actions",
            state_updates={"plan": plan_obj},
        )
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
