"""Audit event persistence-boundary sanitization tests."""

from __future__ import annotations

import json

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.audit.sanitize import sanitize_audit_event
from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.persistence.postgres.audit import (
    append_audit_event,
    build_audit_event,
    hash_event,
)
from safecode.utils.time import utc_now_iso

_SECRET = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"
_REDACTED_TOKEN = "[REDACTED]"


def test_sanitize_audit_event_redacts_secret_fields():
    event = AuditEvent(
        type="command_executed",
        timestamp=utc_now_iso(),
        message=f"token={_SECRET}",
        error=f"failed with {_SECRET}",
        command=f"curl -H 'Authorization: Bearer {_SECRET}'",
        files=[f"/tmp/{_SECRET}.txt"],
        metadata={"token": _SECRET, "scope": "in_scope"},
    )

    sanitized = sanitize_audit_event(event)

    assert _SECRET not in (sanitized.message or "")
    assert _SECRET not in (sanitized.error or "")
    assert _SECRET not in (sanitized.command or "")
    assert all(_SECRET not in path for path in sanitized.files)
    assert _SECRET not in sanitized.metadata["token"]
    assert sanitized.metadata["scope"] == "in_scope"
    assert event.message == f"token={_SECRET}"


def test_sanitize_audit_event_is_idempotent():
    event = AuditEvent(
        type="test",
        timestamp=utc_now_iso(),
        message=f"secret={_SECRET}",
        metadata={"note": "plain text"},
    )
    once = sanitize_audit_event(event)
    twice = sanitize_audit_event(once)
    assert once == twice


def test_sanitize_audit_event_preserves_non_secret_content():
    event = AuditEvent(
        type="workflow_start",
        timestamp="2026-06-20T00:00:00+00:00",
        message="workflow started for run-eval-sql",
        metadata={"run_id": "run-eval-sql", "tenant_id": "local"},
    )
    sanitized = sanitize_audit_event(event)
    assert sanitized == event


def test_audit_logger_persists_redacted_secrets_and_verifies(tmp_path):
    logger = AuditLogger(tmp_path)
    logger.write(
        AuditEvent(
            type="command_executed",
            timestamp=utc_now_iso(),
            message=f"used {_SECRET}",
            error=f"stderr {_SECRET}",
            command=f"export TOKEN={_SECRET}",
            files=[f"notes/{_SECRET}.md"],
            metadata={"token": _SECRET},
        )
    )

    raw = (tmp_path / ".sac" / "logs" / "events.jsonl").read_text(encoding="utf-8")
    assert _SECRET not in raw
    assert _REDACTED_TOKEN in raw
    ok, message = logger.verify_integrity()
    assert ok, message
    stored = logger.read_recent(limit=1)[0]
    assert stored.metadata["token"] == _REDACTED_TOKEN


def test_audit_logger_preserves_task_id_and_chain_with_legacy_event(tmp_path):
    logger = AuditLogger(tmp_path)
    log_file = tmp_path / ".sac" / "logs" / "events.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    legacy = AuditEvent(
        type="legacy_event",
        timestamp="2026-06-19T00:00:00+00:00",
        message=f"legacy secret {_SECRET}",
        metadata={"token": _SECRET},
    )
    legacy.previous_hash = None
    legacy.event_hash = logger._hash_event(legacy)
    log_file.write_text(
        json.dumps(legacy.model_dump(), ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    logger.anchor_store.write(log_file, 1, legacy.event_hash)

    logger.write(
        AuditEvent(
            type="sanitized_event",
            timestamp=utc_now_iso(),
            message=f"new secret {_SECRET}",
            metadata={"token": _SECRET},
        ),
        task_id="task-abc12345",
    )

    ok, message = logger.verify_integrity()
    assert ok, message
    events = logger.iter_events()
    assert len(events) == 2
    assert events[0].message == legacy.message
    assert _SECRET in (events[0].message or "")
    assert _SECRET not in (events[1].message or "")
    assert events[1].metadata["task_id"] == "task-abc12345"
    assert events[1].previous_hash == legacy.event_hash


def test_enterprise_audit_chain_redacts_message_and_payload(tmp_path):
    audit = EnterpriseAuditChain(tmp_path)
    audit.emit(
        AuditEventKind.workflow_start,
        run_id="run-redact01",
        actor_id="user:test",
        message=f"started with {_SECRET}",
        payload={"token": _SECRET, "phase": "collect"},
    )

    raw = audit.log_file.read_text(encoding="utf-8")
    assert _SECRET not in raw
    ok, message = audit.verify_integrity()
    assert ok, message
    event = audit.iter_events()[-1]
    assert _SECRET not in (event.message or "")
    assert event.metadata["token"] == _REDACTED_TOKEN
    assert event.metadata["phase"] == "collect"


def test_postgres_build_audit_event_redacts_before_hash():
    event = build_audit_event(
        AuditEventKind.workflow_start,
        tenant_id="tenant-a",
        run_id="run-pg-redact",
        actor_id="user:test",
        message=f"message {_SECRET}",
        payload={"token": _SECRET, "phase": "plan"},
    )

    assert _SECRET not in (event.message or "")
    assert event.metadata["token"] == _REDACTED_TOKEN
    assert event.metadata["phase"] == "plan"
    assert event.event_hash == hash_event(event)


def test_postgres_build_audit_event_includes_actor_in_metadata():
    event = build_audit_event(
        AuditEventKind.workflow_start,
        tenant_id="tenant-a",
        run_id="run-pg-redact",
        actor_id="user:test",
        message="workflow started",
        payload={"token": _SECRET, "phase": "plan"},
    )

    assert event.metadata["actor_id"] == "user:test"
    assert _SECRET not in (event.message or "")
    assert event.metadata["token"] == _REDACTED_TOKEN
    assert event.event_hash == hash_event(event)


def test_audit_builders_preserve_reserved_metadata_and_redact_actor(tmp_path):
    secret_actor = f"token={_SECRET}"
    payload = {
        "tenant_id": "attacker-tenant",
        "run_id": "run-attacker",
        "actor_id": "user:attacker",
        "chain_id": "attacker-chain",
    }
    local = EnterpriseAuditChain(tmp_path).emit(
        AuditEventKind.workflow_start,
        tenant_id="tenant-a",
        run_id="run-reserved01",
        actor_id=secret_actor,
        payload=payload,
    )
    postgres = build_audit_event(
        AuditEventKind.workflow_start,
        tenant_id="tenant-a",
        run_id="run-reserved01",
        actor_id=secret_actor,
        payload=payload,
    )

    for event in (local, postgres):
        assert event.metadata["tenant_id"] == "tenant-a"
        assert event.metadata["run_id"] == "run-reserved01"
        assert event.metadata["chain_id"] == "enterprise"
        assert _SECRET not in event.metadata["actor_id"]
        assert event.event_hash == hash_event(event)


def test_enterprise_audit_chain_includes_actor_in_hash_covered_metadata(tmp_path):
    audit = EnterpriseAuditChain(tmp_path)
    audit.emit(
        AuditEventKind.workflow_start,
        run_id="run-actor01",
        actor_id="user:security",
        message="started",
    )
    event = audit.iter_events()[-1]
    assert event.metadata["actor_id"] == "user:security"
    ok, message = audit.verify_integrity()
    assert ok, message


def test_postgres_append_audit_event_redacts_direct_writer():
    from unittest.mock import MagicMock

    conn = MagicMock()
    unsanitized = AuditEvent(
        type="workflow_start",
        timestamp=utc_now_iso(),
        message=f"message {_SECRET}",
        metadata={
            "run_id": "run-direct",
            "tenant_id": "tenant-a",
            "actor_id": "user:test",
            "token": _SECRET,
        },
        previous_hash="abc123previous",
        event_hash="stale-hash-should-not-persist",
    )

    head_result = MagicMock()
    head_result.fetchone.return_value = ("abc123previous",)
    conn.execute.side_effect = [MagicMock(), head_result, MagicMock()]

    persisted = append_audit_event(conn, unsanitized, actor_id="user:test")

    assert conn.execute.call_count == 3
    _query, insert_args = conn.execute.call_args_list[-1].args
    serialized_event = insert_args[3]
    assert _SECRET not in serialized_event
    assert persisted.previous_hash == "abc123previous"
    assert insert_args[4] == "abc123previous"
    assert persisted.event_hash == hash_event(persisted)
    assert insert_args[5] == persisted.event_hash
    assert persisted.metadata["token"] == _REDACTED_TOKEN
    assert persisted.metadata["actor_id"] == "user:test"


def test_postgres_append_audit_event_rejects_actor_mismatch():
    from unittest.mock import MagicMock

    import pytest

    conn = MagicMock()
    event = AuditEvent(
        type="workflow_start",
        timestamp=utc_now_iso(),
        metadata={"run_id": "run-direct", "tenant_id": "tenant-a", "actor_id": "user:a"},
    )
    head_result = MagicMock()
    head_result.fetchone.return_value = None
    conn.execute.side_effect = [MagicMock(), head_result]
    with pytest.raises(ValueError, match="actor_id column does not match"):
        append_audit_event(conn, event, actor_id="user:b")


def test_postgres_append_audit_event_rejects_stale_chain_head():
    from unittest.mock import MagicMock

    import pytest

    conn = MagicMock()
    head_result = MagicMock()
    head_result.fetchone.return_value = ("current-head",)
    conn.execute.side_effect = [MagicMock(), head_result]
    event = AuditEvent(
        type="workflow_start",
        timestamp=utc_now_iso(),
        metadata={"run_id": "run-direct", "tenant_id": "tenant-a", "actor_id": "user:a"},
        previous_hash="stale-head",
    )

    with pytest.raises(ValueError, match="previous_hash does not match"):
        append_audit_event(conn, event, actor_id="user:a")
