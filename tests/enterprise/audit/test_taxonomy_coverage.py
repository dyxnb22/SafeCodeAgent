"""Audit taxonomy coverage tests."""

from safecode.enterprise.audit.events import ALL_AUDIT_EVENT_KINDS, AuditEventKind, audit_kind_values


EXPECTED_KINDS = {
    "workflow.start",
    "workflow.end",
    "node.start",
    "node.end",
    "retrieval.query",
    "retrieval.citation_used",
    "model.call_start",
    "model.call_end",
    "model.validation_fail",
    "tool.proposed",
    "tool.blocked",
    "tool.executed",
    "approval.requested",
    "approval.decided",
    "approval.consumed",
    "policy.block",
    "policy.project_override_blocked",
    "sandbox.proposal",
    "sandbox.executed",
    "patch.proposed",
    "patch.applied",
    "rollback.executed",
    "audit.anchor_written",
}


def test_audit_event_kind_values_match_plan():
    assert audit_kind_values() == EXPECTED_KINDS


def test_all_kinds_exposed_in_tuple():
    assert len(ALL_AUDIT_EVENT_KINDS) == len(EXPECTED_KINDS)
    assert AuditEventKind.tool_call_proposed.value == "tool.proposed"
