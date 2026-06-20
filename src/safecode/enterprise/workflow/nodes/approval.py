"""approval_gate 工作流节点（九步流水线第 8 步）。

- **流水线位置**：第 8 步 / 9 — 评估提案是否需人工审批，可中断工作流等待 HITL。
- **输入**：``validation_failed``、``risk_tier``、``proposals``、``request`` 元数据。
- **输出**：需审批时设置 ``status=awaiting_approval`` 与
  ``awaiting_human_approval=True``；校验失败时置 ``blocked``。
- **安全治理**：确定性审批门；高风险、实时 PR 评论、补丁应用或工单发帖须人工批准；
  模型与 Agent 不能自行批准；未消耗审批_grant 前 ``finalize`` 不得执行受控写入。
"""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks import pr_review, remediation, secure_planning
from safecode.enterprise.workflow.types import RiskTier, WorkflowStatus

NODE_NAME = "approval_gate"


async def run(state: EnterpriseRunState) -> NodePatch:
    """根据风险等级与提案类型判定是否进入人工审批等待态。"""
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
    ticket_post = (
        secure_planning.is_secure_planning_task(state)
        and state.request.extra.get("post_to_ticket") == "1"
        and any(item.kind == "ticket" for item in state.proposals)
    )
    patch_apply = remediation.is_remediation_task(state) and any(
        item.kind == "patch" for item in state.proposals
    )
    if secure_planning.is_secure_planning_task(state):
        needs_approval = ticket_post
    else:
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
