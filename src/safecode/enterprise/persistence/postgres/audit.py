"""PostgreSQL audit hash-chain persistence (v2.1.3-T4)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from safecode.audit.models import AuditEvent
from safecode.context.redactor import redact_secrets
from safecode.enterprise.audit.events import AuditEventKind


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hash_event(event: AuditEvent) -> str:
    data = event.model_dump()
    data["event_hash"] = None
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_audit_event(
    kind: AuditEventKind,
    *,
    tenant_id: str,
    run_id: str,
    actor_id: str,
    payload: dict[str, str] | None = None,
    status: str = "success",
    message: str | None = None,
    previous_hash: str | None = None,
) -> AuditEvent:
    metadata = {"run_id": run_id, "chain_id": "enterprise", "tenant_id": tenant_id}
    if payload:
        metadata.update({key: redact_secrets(str(value)) for key, value in payload.items()})
    event = AuditEvent(
        type=kind.value,
        timestamp=utc_now_iso(),
        status=status,
        message=message,
        metadata=metadata,
        trace_id=run_id,
        previous_hash=previous_hash,
    )
    event.event_hash = hash_event(event)
    return event


def last_event_hash(conn: Any) -> str | None:
    row = conn.execute(
        "SELECT event_hash FROM enterprise.audit_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return str(row[0])


def append_audit_event(conn: Any, event: AuditEvent, *, actor_id: str) -> AuditEvent:
    conn.execute(
        """
        INSERT INTO enterprise.audit_events (
            tenant_id, run_id, actor_id, event, previous_hash, event_hash, event_timestamp
        ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
        """,
        (
            event.metadata.get("tenant_id", "local"),
            event.metadata.get("run_id"),
            actor_id,
            json.dumps(event.model_dump(), ensure_ascii=False, sort_keys=True),
            event.previous_hash,
            event.event_hash,
            event.timestamp,
        ),
    )
    return event


def emit_audit_event(
    conn: Any,
    kind: AuditEventKind,
    *,
    tenant_id: str,
    run_id: str,
    actor_id: str,
    payload: dict[str, str] | None = None,
    status: str = "success",
    message: str | None = None,
) -> AuditEvent:
    event = build_audit_event(
        kind,
        tenant_id=tenant_id,
        run_id=run_id,
        actor_id=actor_id,
        payload=payload,
        status=status,
        message=message,
        previous_hash=last_event_hash(conn),
    )
    return append_audit_event(conn, event, actor_id=actor_id)


def verify_audit_chain(conn: Any) -> tuple[bool, str]:
    rows = conn.execute(
        "SELECT event FROM enterprise.audit_events ORDER BY id ASC"
    ).fetchall()
    if not rows:
        return True, "No audit events found."

    previous_hash: str | None = None
    for index, row in enumerate(rows, start=1):
        try:
            event = AuditEvent(**row[0])
        except (ValidationError, TypeError, ValueError) as exc:
            return False, f"Audit event parse error at row {index}: {exc}"
        if not event.event_hash:
            return False, f"Audit event without hash at row {index}."
        if event.previous_hash != previous_hash:
            return False, f"Audit hash chain break at row {index}."
        expected_hash = hash_event(event)
        if event.event_hash != expected_hash:
            return False, f"Audit event hash mismatch at row {index}."
        previous_hash = event.event_hash
    return True, "Audit chain integrity verified."


def list_audit_events(
    conn: Any,
    *,
    tenant_id: str,
    run_id: str | None = None,
) -> list[AuditEvent]:
    if run_id is None:
        rows = conn.execute(
            """
            SELECT event FROM enterprise.audit_events
            WHERE tenant_id = %s
            ORDER BY id ASC
            """,
            (tenant_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT event FROM enterprise.audit_events
            WHERE tenant_id = %s AND run_id = %s
            ORDER BY id ASC
            """,
            (tenant_id, run_id),
        ).fetchall()
    return [AuditEvent(**row[0]) for row in rows]


def tamper_first_audit_event(conn: Any) -> None:
    row = conn.execute(
        "SELECT id, event FROM enterprise.audit_events ORDER BY id ASC LIMIT 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("no audit events to tamper")
    event_id, payload = row
    event = dict(payload)
    event["message"] = "tampered"
    conn.execute(
        "UPDATE enterprise.audit_events SET event = %s::jsonb WHERE id = %s",
        (json.dumps(event, ensure_ascii=False, sort_keys=True), event_id),
    )
