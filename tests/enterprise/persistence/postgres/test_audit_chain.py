"""PostgreSQL audit hash-chain durability tests (v2.1.3-T4)."""

from __future__ import annotations

import pytest

from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.persistence.postgres.audit import list_audit_events

pytestmark = pytest.mark.postgres_integration


def test_postgres_audit_chain_verifies_after_append(postgres_backend) -> None:
    audit = postgres_backend.audit
    audit.emit(
        AuditEventKind.workflow_start,
        tenant_id="tenant-a",
        run_id="run-pgaudit001",
        actor_id="user:test",
    )
    audit.emit(
        AuditEventKind.workflow_end,
        tenant_id="tenant-a",
        run_id="run-pgaudit001",
        actor_id="user:test",
    )
    ok, message = audit.verify_integrity()
    assert ok, message
    events = audit.list_events(tenant_id="tenant-a", run_id="run-pgaudit001")
    assert len(events) == 2


def test_postgres_tampering_breaks_chain(postgres_backend) -> None:
    from tests.enterprise.helpers.audit_tamper import tamper_first_postgres_audit

    audit = postgres_backend.audit
    audit.emit(
        AuditEventKind.workflow_start,
        tenant_id="tenant-a",
        run_id="run-pgaudit002",
        actor_id="user:test",
    )
    tamper_first_postgres_audit(postgres_backend)
    ok, _message = audit.verify_integrity()
    assert not ok


def test_local_and_postgres_audit_event_order_matches(
    postgres_backend, tmp_path
) -> None:
    run_id = "run-pgaudit003"
    tenant_id = "tenant-a"
    kinds = [AuditEventKind.workflow_start, AuditEventKind.approval_requested]

    local = EnterpriseAuditChain(tmp_path)
    for kind in kinds:
        local.emit(kind, tenant_id=tenant_id, run_id=run_id, actor_id="user:test")

    pg = postgres_backend.audit
    for kind in kinds:
        pg.emit(kind, tenant_id=tenant_id, run_id=run_id, actor_id="user:test")

    local_events = [
        event
        for event in local.iter_events()
        if event.metadata.get("tenant_id") == tenant_id and event.metadata.get("run_id") == run_id
    ]
    pg_events = pg.list_events(tenant_id=tenant_id, run_id=run_id)
    assert [event.type for event in local_events] == [event.type for event in pg_events]
    assert all(event.event_hash for event in pg_events)

    with postgres_backend.pool.connection() as conn:
        raw_rows = list_audit_events(conn, tenant_id=tenant_id, run_id=run_id)
    assert len(raw_rows) == len(kinds)
