"""Sanitize audit events before hash-chain persistence."""

from __future__ import annotations

from safecode.audit.models import AuditEvent
from safecode.context.redactor import redact_secrets

_PERSISTENCE_STRING_FIELDS = ("message", "error", "command")


def _redact_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return redact_secrets(value)


def sanitize_audit_event(event: AuditEvent) -> AuditEvent:
    """Return an audit event with secret-like fields redacted for persistence."""
    updates: dict[str, object] = {}
    for field in _PERSISTENCE_STRING_FIELDS:
        current = getattr(event, field)
        redacted = _redact_optional(current)
        if redacted != current:
            updates[field] = redacted
    if event.files:
        redacted_files = [redact_secrets(str(path)) for path in event.files]
        if redacted_files != event.files:
            updates["files"] = redacted_files
    if event.metadata:
        redacted_metadata = {
            str(key): redact_secrets(str(value)) for key, value in event.metadata.items()
        }
        if redacted_metadata != event.metadata:
            updates["metadata"] = redacted_metadata
    if not updates:
        return event
    return event.model_copy(update=updates)


def apply_audit_event_sanitization(event: AuditEvent) -> None:
    """Mutate *event* in place with sanitized persistence fields."""
    sanitized = sanitize_audit_event(event)
    if sanitized is event:
        return
    for field in _PERSISTENCE_STRING_FIELDS:
        setattr(event, field, getattr(sanitized, field))
    event.files = sanitized.files
    event.metadata = sanitized.metadata
