"""Sanitize audit events before hash-chain persistence.

中文模块说明：审计事件持久化前脱敏。
- 对 message/error/command、files、metadata 等字段调用 redact_secrets，避免密钥进入哈希链与磁盘。
- 脱敏在 write() 计算哈希之前执行，保证链上存的是已脱敏内容。
"""

from __future__ import annotations

from safecode.audit.models import AuditEvent
from safecode.context.redactor import redact_secrets

_PERSISTENCE_STRING_FIELDS = ("message", "error", "command", "patch_id", "checkpoint_id", "trace_id")


def _redact_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return redact_secrets(value)


def sanitize_audit_event(event: AuditEvent) -> AuditEvent:
    """Return an audit event with secret-like fields redacted for persistence.

    返回脱敏后的新副本；无敏感内容时返回原对象引用。
    """
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
        # metadata 值统一转 str 再脱敏；嵌套结构不会递归展开，复杂对象可能漏脱敏。
        redacted_metadata = {
            str(key): redact_secrets(str(value)) for key, value in event.metadata.items()
        }
        if redacted_metadata != event.metadata:
            updates["metadata"] = redacted_metadata
    if not updates:
        return event
    return event.model_copy(update=updates)


def apply_audit_event_sanitization(event: AuditEvent) -> None:
    """Mutate *event* in place with sanitized persistence fields.

    原地脱敏，供 AuditLogger.write 在哈希前调用；不改变 AuditEvent 字段集合。
    """
    sanitized = sanitize_audit_event(event)
    if sanitized is event:
        return
    for field in _PERSISTENCE_STRING_FIELDS:
        setattr(event, field, getattr(sanitized, field))
    event.files = sanitized.files
    event.metadata = sanitized.metadata
