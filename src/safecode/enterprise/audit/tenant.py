"""Tenant-scoped audit event filtering."""

from __future__ import annotations

from safecode.audit.models import AuditEvent


def audit_event_tenant(event: AuditEvent, *, default: str = "local") -> str:
    return str(event.metadata.get("tenant_id") or default)


def filter_audit_events_by_tenant(
    events: list[AuditEvent],
    tenant_id: str,
    *,
    run_id: str | None = None,
) -> list[AuditEvent]:
    """Return audit events for a tenant, optionally scoped to one run."""
    filtered: list[AuditEvent] = []
    for event in events:
        if audit_event_tenant(event) != tenant_id:
            continue
        if run_id is not None and event.metadata.get("run_id") != run_id:
            continue
        filtered.append(event)
    return filtered
