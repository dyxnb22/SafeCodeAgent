"""PostgreSQL audit chain concurrency tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock

import pytest

from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.persistence.postgres.audit import (
    ENTERPRISE_GLOBAL_AUDIT_CHAIN_LOCK_KEY,
    emit_audit_event,
    verify_audit_chain,
)


def test_emit_audit_event_acquires_global_advisory_lock_unit() -> None:
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None
    emit_audit_event(
        conn,
        AuditEventKind.workflow_start,
        tenant_id="tenant-a",
        run_id="run-lock-unit",
        actor_id="user:test",
    )
    conn.execute.assert_any_call(
        "SELECT pg_advisory_xact_lock(%s)",
        (ENTERPRISE_GLOBAL_AUDIT_CHAIN_LOCK_KEY,),
    )


@pytest.mark.postgres_integration
def test_parallel_pg_audit_emits_form_one_linear_chain(postgres_backend) -> None:
    audit = postgres_backend.audit
    workers = 12
    barrier = __import__("threading").Barrier(workers)

    def emit_once(index: int) -> None:
        barrier.wait()
        audit.emit(
            AuditEventKind.workflow_start,
            tenant_id="tenant-a",
            run_id=f"run-pg-chain-{index:02d}",
            actor_id="user:test",
            message=f"parallel-{index}",
        )

    for _ in range(10):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(emit_once, index) for index in range(workers)]
            for future in as_completed(futures):
                future.result()
        with postgres_backend._uow.connection() as conn:
            ok, message = verify_audit_chain(conn)
            assert ok, message
            rows = conn.execute(
                "SELECT previous_hash, event_hash FROM enterprise.audit_events ORDER BY id ASC"
            ).fetchall()
        previous = None
        for row in rows:
            assert row[0] == previous
            previous = row[1]
