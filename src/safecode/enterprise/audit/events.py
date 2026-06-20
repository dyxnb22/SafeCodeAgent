"""Enterprise audit event taxonomy.

企业审计事件分类：覆盖工作流、检索、模型、工具、审批、策略、沙箱、补丁全生命周期。
模型相关事件（model_call_*）仅表观测，不授予执行权；审批事件须可关联 request/grant ID。
"""

from __future__ import annotations

from enum import Enum


class AuditEventKind(str, Enum):
    """审计事件种类枚举，写入哈希链供合规追溯。"""

    workflow_start = "workflow.start"
    workflow_end = "workflow.end"
    node_start = "node.start"
    node_end = "node.end"
    retrieval_query = "retrieval.query"  # RAG 查询（须记录权限裁决）
    retrieval_citation_used = "retrieval.citation_used"  # 引用被采用（来源可追溯）
    model_call_start = "model.call_start"  # 模型调用开始（非执行授权）
    model_call_end = "model.call_end"
    model_validation_fail = "model.validation_fail"  # 模型输出校验失败
    tool_call_proposed = "tool.proposed"  # 工具提案（模型输出，待门控）
    tool_call_blocked = "tool.blocked"  # 策略/RBAC 阻断
    tool_call_executed = "tool.executed"  # 经审批后实际执行
    approval_requested = "approval.requested"
    approval_decided = "approval.decided"
    approval_consumed = "approval.consumed"  # 单次 grant 消费
    policy_block = "policy.block"  # 策略层阻断
    project_override_blocked = "policy.project_override_blocked"  # 项目层弱化被阻断
    sandbox_proposal = "sandbox.proposal"
    sandbox_executed = "sandbox.executed"
    patch_proposed = "patch.proposed"  # 补丁提案（模型输出）
    patch_applied = "patch.applied"  # 经审批后应用
    rollback_executed = "rollback.executed"
    audit_anchor_written = "audit.anchor_written"


ALL_AUDIT_EVENT_KINDS: tuple[AuditEventKind, ...] = tuple(AuditEventKind)


def audit_kind_values() -> set[str]:
    return {item.value for item in AuditEventKind}
