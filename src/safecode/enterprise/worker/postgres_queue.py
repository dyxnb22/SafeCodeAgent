"""Postgres-backed command queue (v2.1.5-T1)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from safecode.enterprise.persistence.postgres.unit_of_work import UnitOfWork
from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.worker.models import QueueJob, RunCommandKind, RunCommandRecord
from safecode.enterprise.worker.queue import (
    IdempotencyConflictError,
    MAX_QUEUE_ATTEMPTS,
    _job_id,
    _redact_queue_error,
    _utc_now,
    _validate_idempotency_key,
)


@dataclass(frozen=True)
class PostgresCommandQueue:
    uow: UnitOfWork

    def get_command(
        self, *, tenant_id: str, idempotency_key: str
    ) -> RunCommandRecord | None:
        tenant = validate_tenant_id(tenant_id)
        key = _validate_idempotency_key(idempotency_key)
        with self.uow.connection() as conn:
            row = conn.execute(
                """
                SELECT tenant_id, idempotency_key, command, run_id, payload, created_at
                FROM enterprise.run_commands
                WHERE tenant_id = %s AND idempotency_key = %s
                """,
                (tenant, key),
            ).fetchone()
        if row is None:
            return None
        return RunCommandRecord(
            tenant_id=str(row[0]),
            idempotency_key=str(row[1]),
            command=row[2],  # type: ignore[arg-type]
            run_id=str(row[3]),
            payload=dict(row[4] or {}),
            created_at=row[5].isoformat().replace("+00:00", "+00:00"),
        )

    def record_command(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        command: RunCommandKind,
        run_id: str,
        payload: dict[str, str] | None = None,
    ) -> RunCommandRecord:
        tenant = validate_tenant_id(tenant_id)
        key = _validate_idempotency_key(idempotency_key)
        existing = self.get_command(tenant_id=tenant, idempotency_key=key)
        if existing is not None:
            if existing.command != command or existing.run_id != run_id:
                raise IdempotencyConflictError(
                    f"idempotency key {key!r} already bound to another command"
                )
            return existing
        record = RunCommandRecord(
            tenant_id=tenant,
            idempotency_key=key,
            command=command,
            run_id=run_id,
            payload=dict(payload or {}),
            created_at=_utc_now(),
        )
        with self.uow.connection() as conn:
            conn.execute(
                """
                INSERT INTO enterprise.run_commands (
                    tenant_id, idempotency_key, command, run_id, payload, created_at
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    tenant,
                    key,
                    command,
                    run_id,
                    json.dumps(record.payload),
                    record.created_at,
                ),
            )
            conn.commit()
        return record

    def enqueue_job(
        self,
        *,
        tenant_id: str,
        run_id: str,
        command: RunCommandKind,
        payload: dict[str, str] | None = None,
    ) -> QueueJob:
        tenant = validate_tenant_id(tenant_id)
        job = QueueJob(
            job_id=_job_id(),
            tenant_id=tenant,
            run_id=run_id,
            command=command,
            status="pending",
            payload=dict(payload or {}),
            created_at=_utc_now(),
        )
        with self.uow.connection() as conn:
            conn.execute(
                """
                INSERT INTO enterprise.queue (
                    job_id, tenant_id, run_id, command, status, payload, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    job.job_id,
                    tenant,
                    run_id,
                    command,
                    job.status,
                    json.dumps(job.payload),
                    job.created_at,
                ),
            )
            conn.commit()
        return job

    def poll_pending_job(self) -> QueueJob | None:
        with self.uow.connection() as conn:
            row = conn.execute(
                """
                SELECT job_id, tenant_id, run_id, command, status, payload, created_at
                FROM enterprise.queue
                WHERE status = 'pending'
                ORDER BY created_at ASC, job_id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE enterprise.queue SET status = 'leased' WHERE job_id = %s",
                (row[0],),
            )
            conn.commit()
        return QueueJob(
            job_id=str(row[0]),
            tenant_id=str(row[1]),
            run_id=str(row[2]),
            command=row[3],  # type: ignore[arg-type]
            status="pending",
            payload=dict(row[5] or {}),
            created_at=row[6].isoformat().replace("+00:00", "+00:00"),
        )

    def complete_job(self, job_id: str) -> None:
        with self.uow.connection() as conn:
            conn.execute(
                """
                UPDATE enterprise.queue
                SET status = 'completed', completed_at = NOW()
                WHERE job_id = %s
                """,
                (job_id,),
            )
            conn.commit()

    def fail_job(self, job_id: str, *, message: str) -> None:
        redacted = _redact_queue_error(message)
        with self.uow.connection() as conn:
            conn.execute(
                """
                UPDATE enterprise.queue
                SET status = 'failed',
                    payload = payload || %s::jsonb,
                    completed_at = NOW()
                WHERE job_id = %s
                """,
                (json.dumps({"error": redacted}), job_id),
            )
            conn.commit()

    def retry_job(self, job_id: str, *, message: str) -> bool:
        redacted = _redact_queue_error(message)
        with self.uow.connection() as conn:
            row = conn.execute(
                "SELECT attempts FROM enterprise.queue WHERE job_id = %s",
                (job_id,),
            ).fetchone()
            if row is None:
                return False
            next_attempts = int(row[0]) + 1
            if next_attempts >= MAX_QUEUE_ATTEMPTS:
                return False
            conn.execute(
                """
                UPDATE enterprise.queue
                SET status = 'pending',
                    attempts = %s,
                    payload = payload || %s::jsonb
                WHERE job_id = %s
                """,
                (next_attempts, json.dumps({"last_error": redacted}), job_id),
            )
            conn.commit()
        return True

    def dlq_job(self, job_id: str, *, message: str, poison: bool = False) -> None:
        redacted = _redact_queue_error(message)
        with self.uow.connection() as conn:
            row = conn.execute(
                """
                SELECT job_id, tenant_id, run_id, command, payload, attempts, created_at
                FROM enterprise.queue
                WHERE job_id = %s
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                return
            conn.execute(
                """
                INSERT INTO enterprise.dlq (
                    job_id, tenant_id, run_id, command, payload, attempts,
                    poison, error_message, created_at
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                """,
                (
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    json.dumps(dict(row[4] or {})),
                    int(row[5]),
                    poison,
                    redacted,
                    row[6],
                ),
            )
            conn.execute("DELETE FROM enterprise.queue WHERE job_id = %s", (job_id,))
            conn.commit()
