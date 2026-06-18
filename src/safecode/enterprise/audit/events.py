"""Enterprise audit event taxonomy."""

from __future__ import annotations

from enum import Enum


class AuditEventKind(str, Enum):
    workflow_start = "workflow.start"
    workflow_end = "workflow.end"
    node_start = "node.start"
    node_end = "node.end"
    retrieval_query = "retrieval.query"
    retrieval_citation_used = "retrieval.citation_used"
    model_call_start = "model.call_start"
    model_call_end = "model.call_end"
    model_validation_fail = "model.validation_fail"
    tool_call_proposed = "tool.proposed"
    tool_call_blocked = "tool.blocked"
    tool_call_executed = "tool.executed"
    approval_requested = "approval.requested"
    approval_decided = "approval.decided"
    approval_consumed = "approval.consumed"
    policy_block = "policy.block"
    project_override_blocked = "policy.project_override_blocked"
    sandbox_proposal = "sandbox.proposal"
    sandbox_executed = "sandbox.executed"
    patch_proposed = "patch.proposed"
    patch_applied = "patch.applied"
    rollback_executed = "rollback.executed"
    audit_anchor_written = "audit.anchor_written"


ALL_AUDIT_EVENT_KINDS: tuple[AuditEventKind, ...] = tuple(AuditEventKind)


def audit_kind_values() -> set[str]:
    return {item.value for item in AuditEventKind}
