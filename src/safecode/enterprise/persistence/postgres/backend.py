"""PostgreSQL persistence adapter implementing v2.1.2 repository protocols."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from psycopg import IsolationLevel
from psycopg.errors import SerializationFailure
from psycopg_pool import ConnectionPool

from safecode.audit.models import AuditEvent
from safecode.context.redactor import redact_secrets
from safecode.enterprise.approvals.store import (
    Action,
    ApprovalRequest,
    Grant,
    GrantAlreadyConsumedError,
    grant_hash,
    grant_id_for_request,
    request_hash,
    validate_grant_id,
    validate_request_id,
)
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.eval.cases import EvaluationResult
from safecode.enterprise.persistence.postgres import audit as pg_audit
from safecode.enterprise.persistence.postgres.evidence import export_run_evidence_from_pg
from safecode.enterprise.persistence.postgres.migrate import apply_migrations
from safecode.enterprise.persistence.postgres.unit_of_work import UnitOfWork
from safecode.enterprise.persistence.webhook_store import PostgresWebhookEventStore
from safecode.enterprise.worker.lease import PostgresRunLeaseStore
from safecode.enterprise.persistence.protocols import (
    ApprovalDecision,
    assert_tenant_match,
    validate_tenant_id,
)
from safecode.enterprise.trace.emitter import TraceEmitter
from safecode.enterprise.trace.events import TraceEvent, TraceEventType
from safecode.enterprise.trace.timeline import write_timeline
from safecode.enterprise.workflow.checkpoint import (
    RunCheckpoint,
    gc_runs as gc_runs_files,
    load_checkpoint as load_checkpoint_file,
    save_checkpoint as save_checkpoint_file,
)
from safecode.enterprise.workflow.contracts import NodeCost
from safecode.enterprise.workflow.exceptions import (
    ApprovalRequestExistsError,
    ApprovalRequestNotFoundError,
    ApprovalRequestTamperedError,
    CheckpointCorruptedError,
    InvalidRunIdError,
    RequestAlreadyConsumedError,
)
from safecode.enterprise.workflow.ids import validate_run_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PostgresRunStore:
    def __init__(self, uow: UnitOfWork, artifacts_root: Path) -> None:
        self._uow = uow
        self._artifacts_root = artifacts_root

    def save_checkpoint(self, *, tenant_id: str, checkpoint: RunCheckpoint) -> None:
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, checkpoint.state.tenant_id, operation="save_checkpoint")
        save_checkpoint_file(self._artifacts_root, checkpoint)
        with self._uow.connection() as conn:
            conn.execute(
                """
                INSERT INTO enterprise.checkpoints (
                    tenant_id, run_id, schema_version, completed_nodes, next_node, state, updated_at
                ) VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb, NOW())
                ON CONFLICT (tenant_id, run_id) DO UPDATE SET
                    schema_version = EXCLUDED.schema_version,
                    completed_nodes = EXCLUDED.completed_nodes,
                    next_node = EXCLUDED.next_node,
                    state = EXCLUDED.state,
                    updated_at = NOW()
                """,
                (
                    tenant,
                    checkpoint.run_id,
                    checkpoint.schema_version,
                    json.dumps(list(checkpoint.completed_nodes)),
                    checkpoint.next_node,
                    checkpoint.state.model_dump_json(),
                ),
            )
            conn.commit()

    def load_checkpoint(self, *, tenant_id: str, run_id: str) -> RunCheckpoint:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        with self._uow.connection() as conn:
            row = conn.execute(
                """
                SELECT schema_version, run_id, completed_nodes, next_node, state
                FROM enterprise.checkpoints
                WHERE tenant_id = %s AND run_id = %s
                """,
                (tenant, run_id),
            ).fetchone()
        if row is None:
            with self._uow.connection() as conn:
                other = conn.execute(
                    """
                    SELECT tenant_id FROM enterprise.checkpoints
                    WHERE run_id = %s
                    LIMIT 2
                    """,
                    (run_id,),
                ).fetchall()
            if other:
                assert_tenant_match(tenant, str(other[0][0]), operation="load_checkpoint")
            raise CheckpointCorruptedError(f"missing checkpoint for run {run_id!r}")
        from safecode.enterprise.workflow.state import EnterpriseRunState

        schema_version, loaded_run_id, completed_nodes, next_node, state_payload = row
        state = EnterpriseRunState.model_validate(state_payload)
        checkpoint = RunCheckpoint(
            schema_version=str(schema_version),
            run_id=str(loaded_run_id),
            completed_nodes=list(completed_nodes),
            next_node=next_node,
            state=state,
        )
        assert_tenant_match(tenant, checkpoint.state.tenant_id, operation="load_checkpoint")
        return checkpoint

    def resolve_run_tenant(self, *, run_id: str) -> str:
        validate_run_id(run_id)
        with self._uow.connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT tenant_id FROM enterprise.checkpoints
                WHERE run_id = %s
                """,
                (run_id,),
            ).fetchall()
        if len(rows) != 1:
            raise CheckpointCorruptedError(
                f"cannot resolve unique tenant for run {run_id!r}; found {len(rows)}"
            )
        return validate_tenant_id(str(rows[0][0]))

    def purge_run(self, *, tenant_id: str, run_id: str) -> None:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        directory = self._artifacts_root / "enterprise" / "runs" / run_id
        if directory.is_dir() and (directory / "state.json").is_file():
            checkpoint = load_checkpoint_file(self._artifacts_root, run_id)
            assert_tenant_match(tenant, checkpoint.state.tenant_id, operation="purge_run")
        with self._uow.connection() as conn:
            for table in (
                "trace_events",
                "eval_results",
                "evidence_index",
                "grants",
                "approval_requests",
                "checkpoints",
            ):
                conn.execute(
                    f"DELETE FROM enterprise.{table} WHERE tenant_id = %s AND run_id = %s",
                    (tenant, run_id),
                )
            conn.commit()
        if directory.is_dir():
            shutil.rmtree(directory)

    def gc_runs(self, *, tenant_id: str, older_than_days: int) -> list[str]:
        tenant = validate_tenant_id(tenant_id)
        removed_files = gc_runs_files(self._artifacts_root, older_than_days=older_than_days)
        if older_than_days < 1:
            raise ValueError("older_than_days must be at least 1")
        with self._uow.connection() as conn:
            rows = conn.execute(
                """
                DELETE FROM enterprise.checkpoints
                WHERE tenant_id = %s
                  AND updated_at < NOW() - (%s || ' days')::interval
                RETURNING run_id
                """,
                (tenant, str(older_than_days)),
            ).fetchall()
            conn.commit()
        pg_removed = [str(row[0]) for row in rows]
        return sorted(set(removed_files) | set(pg_removed))


class PostgresApprovalStore:
    def __init__(self, uow: UnitOfWork, artifacts_root: Path) -> None:
        self._uow = uow
        self._artifacts_root = artifacts_root

    def _load_request_row(
        self, conn, *, tenant_id: str, run_id: str, request_id: str
    ) -> ApprovalRequest:
        row = conn.execute(
            """
            SELECT payload FROM enterprise.approval_requests
            WHERE tenant_id = %s AND run_id = %s AND request_id = %s
            """,
            (tenant_id, run_id, request_id),
        ).fetchone()
        if row is None:
            raise ApprovalRequestNotFoundError(f"approval request not found: {request_id}")
        request = ApprovalRequest.model_validate(row[0])
        if request.request_hash != request_hash(request):
            raise ApprovalRequestTamperedError(f"approval request tampered: {request_id}")
        return request

    def _load_request_row_for_update(
        self, conn, *, tenant_id: str, run_id: str, request_id: str
    ) -> ApprovalRequest:
        row = conn.execute(
            """
            SELECT payload FROM enterprise.approval_requests
            WHERE tenant_id = %s AND run_id = %s AND request_id = %s
            FOR UPDATE
            """,
            (tenant_id, run_id, request_id),
        ).fetchone()
        if row is None:
            raise ApprovalRequestNotFoundError(f"approval request not found: {request_id}")
        request = ApprovalRequest.model_validate(row[0])
        if request.request_hash != request_hash(request):
            raise ApprovalRequestTamperedError(f"approval request tampered: {request_id}")
        return request

    def save_request(self, *, tenant_id: str, request: ApprovalRequest) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, request.tenant_id, operation="save_request")
        validate_request_id(request.request_id)
        redacted = request.model_copy(update={"preview": redact_secrets(request.preview)[:4096]})
        redacted = redacted.model_copy(update={"request_hash": request_hash(redacted)})
        with self._uow.connection() as conn:
            exists = conn.execute(
                """
                SELECT 1 FROM enterprise.approval_requests
                WHERE tenant_id = %s AND run_id = %s AND request_id = %s
                """,
                (tenant, request.run_id, request.request_id),
            ).fetchone()
            if exists:
                raise ApprovalRequestExistsError(f"approval request exists: {request.request_id}")
            conn.execute(
                """
                INSERT INTO enterprise.approval_requests (
                    tenant_id, run_id, request_id, payload, status, created_at
                ) VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    tenant,
                    request.run_id,
                    request.request_id,
                    redacted.model_dump_json(),
                    redacted.status,
                    redacted.created_at,
                ),
            )
            conn.commit()
        return redacted

    def load_request(
        self, *, tenant_id: str, run_id: str, request_id: str
    ) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        validate_request_id(request_id)
        with self._uow.connection() as conn:
            request = self._load_request_row(
                conn, tenant_id=tenant, run_id=run_id, request_id=request_id
            )
        assert_tenant_match(tenant, request.tenant_id, operation="load_request")
        return request

    def list_requests(self, *, tenant_id: str, run_id: str) -> list[ApprovalRequest]:
        tenant = validate_tenant_id(tenant_id)
        with self._uow.connection() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM enterprise.approval_requests
                WHERE tenant_id = %s AND run_id = %s
                ORDER BY request_id ASC
                """,
                (tenant, run_id),
            ).fetchall()
        items: list[ApprovalRequest] = []
        for row in rows:
            request = ApprovalRequest.model_validate(row[0])
            if request.request_hash != request_hash(request):
                raise ApprovalRequestTamperedError(
                    f"approval request tampered: {request.request_id}"
                )
            items.append(request)
        return items

    def list_pending_requests(self, *, tenant_id: str, run_id: str) -> list[ApprovalRequest]:
        return [item for item in self.list_requests(tenant_id=tenant_id, run_id=run_id) if item.status == "pending"]

    def decide_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision: ApprovalDecision,
        decision_actor: str,
        decision_note: str = "",
    ) -> ApprovalRequest:
        if decision_actor.startswith("model:"):
            raise PermissionError("model actors cannot approve their own requests")
        tenant = validate_tenant_id(tenant_id)
        updated: ApprovalRequest | None = None
        for _attempt in range(8):
            try:
                with self._uow.transaction(isolation_level=IsolationLevel.SERIALIZABLE) as conn:
                    request = self._load_request_row_for_update(
                        conn, tenant_id=tenant, run_id=run_id, request_id=request_id
                    )
                    if request.status not in {"pending", "evidence_requested"} and decision in {
                        "approved",
                        "rejected",
                    }:
                        raise RequestAlreadyConsumedError(
                            f"approval request already decided: {request_id}"
                        )
                    if decision == "revoked" and request.status not in {
                        "pending",
                        "evidence_requested",
                        "approved",
                    }:
                        raise RequestAlreadyConsumedError(
                            f"approval request cannot be revoked: {request_id}"
                        )
                    updated = request.model_copy(
                        update={
                            "status": decision,
                            "decision_at": _utc_now(),
                            "decision_actor": decision_actor,
                            "decision_note": redact_secrets(decision_note),
                        }
                    )
                    updated = updated.model_copy(update={"request_hash": request_hash(updated)})
                    conn.execute(
                        """
                        UPDATE enterprise.approval_requests
                        SET payload = %s::jsonb, status = %s
                        WHERE tenant_id = %s AND run_id = %s AND request_id = %s
                        """,
                        (
                            updated.model_dump_json(),
                            updated.status,
                            tenant,
                            run_id,
                            request_id,
                        ),
                    )
                    if decision == "approved":
                        grant = Grant(
                            grant_id=grant_id_for_request(updated),
                            run_id=updated.run_id,
                            request_id=updated.request_id,
                            tenant_id=updated.tenant_id,
                            action=updated.action,
                            policy_snapshot_id=updated.policy_snapshot_id,
                            target=updated.target,
                            created_at=updated.decision_at or _utc_now(),
                        )
                        stored = grant.model_copy(update={"grant_hash": grant_hash(grant)})
                        conn.execute(
                            """
                            INSERT INTO enterprise.grants (
                                tenant_id, run_id, grant_id, request_id, payload, created_at
                            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                            """,
                            (
                                tenant,
                                grant.run_id,
                                grant.grant_id,
                                grant.request_id,
                                stored.model_dump_json(),
                                stored.created_at,
                            ),
                        )
                    elif decision == "revoked" and request.status == "approved":
                        grant_id = grant_id_for_request(request)
                        row = conn.execute(
                            """
                            SELECT payload FROM enterprise.grants
                            WHERE tenant_id = %s AND run_id = %s AND grant_id = %s
                            FOR UPDATE
                            """,
                            (tenant, run_id, grant_id),
                        ).fetchone()
                        if row is None:
                            raise ApprovalRequestNotFoundError(f"grant not found: {grant_id}")
                        grant = Grant.model_validate(row[0])
                        if grant.grant_hash != grant_hash(grant):
                            raise ApprovalRequestTamperedError(f"grant tampered: {grant_id}")
                        revoked = grant.model_copy(
                            update={"revoked_at": updated.decision_at or _utc_now()}
                        )
                        revoked = revoked.model_copy(update={"grant_hash": grant_hash(revoked)})
                        conn.execute(
                            """
                            UPDATE enterprise.grants
                            SET payload = %s::jsonb, revoked_at = NOW()
                            WHERE tenant_id = %s AND run_id = %s AND grant_id = %s
                            """,
                            (revoked.model_dump_json(), tenant, run_id, grant_id),
                        )
            except SerializationFailure:
                continue
            break
        else:
            raise RequestAlreadyConsumedError(f"approval request already decided: {request_id}")
        assert updated is not None
        assert_tenant_match(tenant, updated.tenant_id, operation="decide_request")
        return updated

    def request_evidence(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision_actor: str,
        decision_note: str,
    ) -> ApprovalRequest:
        if not decision_note.strip():
            raise ValueError("evidence request requires a note")
        return self.decide_request(
            tenant_id=tenant_id,
            run_id=run_id,
            request_id=request_id,
            decision="evidence_requested",
            decision_actor=decision_actor,
            decision_note=decision_note,
        )

    def revoke_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision_actor: str,
        decision_note: str = "",
    ) -> ApprovalRequest:
        return self.decide_request(
            tenant_id=tenant_id,
            run_id=run_id,
            request_id=request_id,
            decision="revoked",
            decision_actor=decision_actor,
            decision_note=decision_note,
        )

    def _load_grant_row(
        self, conn, *, tenant_id: str, run_id: str, grant_id: str
    ) -> Grant:
        row = conn.execute(
            """
            SELECT payload FROM enterprise.grants
            WHERE tenant_id = %s AND run_id = %s AND grant_id = %s
            """,
            (tenant_id, run_id, grant_id),
        ).fetchone()
        if row is None:
            raise ApprovalRequestNotFoundError(f"grant not found: {grant_id}")
        grant = Grant.model_validate(row[0])
        if grant.grant_hash != grant_hash(grant):
            raise ApprovalRequestTamperedError(f"grant tampered: {grant_id}")
        return grant

    def save_grant(self, *, tenant_id: str, grant: Grant) -> Grant:
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, grant.tenant_id, operation="save_grant")
        validate_grant_id(grant.grant_id)
        stored = grant.model_copy(update={"grant_hash": grant_hash(grant)})
        with self._uow.connection() as conn:
            exists = conn.execute(
                """
                SELECT 1 FROM enterprise.grants
                WHERE tenant_id = %s AND run_id = %s AND grant_id = %s
                """,
                (tenant, grant.run_id, grant.grant_id),
            ).fetchone()
            if exists:
                raise ApprovalRequestExistsError(f"grant exists: {grant.grant_id}")
            conn.execute(
                """
                INSERT INTO enterprise.grants (
                    tenant_id, run_id, grant_id, request_id, payload, created_at
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    tenant,
                    grant.run_id,
                    grant.grant_id,
                    grant.request_id,
                    stored.model_dump_json(),
                    stored.created_at,
                ),
            )
            conn.commit()
        return stored

    def load_grant(self, *, tenant_id: str, run_id: str, grant_id: str) -> Grant:
        tenant = validate_tenant_id(tenant_id)
        validate_grant_id(grant_id)
        with self._uow.connection() as conn:
            grant = self._load_grant_row(conn, tenant_id=tenant, run_id=run_id, grant_id=grant_id)
        assert_tenant_match(tenant, grant.tenant_id, operation="load_grant")
        return grant

    def consume_grant(self, *, tenant_id: str, run_id: str, grant_id: str) -> Grant:
        tenant = validate_tenant_id(tenant_id)
        validate_grant_id(grant_id)
        for _attempt in range(8):
            try:
                with self._uow.transaction(isolation_level=IsolationLevel.SERIALIZABLE) as conn:
                    row = conn.execute(
                        """
                        SELECT payload, consumed_at, revoked_at
                        FROM enterprise.grants
                        WHERE tenant_id = %s AND run_id = %s AND grant_id = %s
                        FOR UPDATE
                        """,
                        (tenant, run_id, grant_id),
                    ).fetchone()
                    if row is None:
                        raise ApprovalRequestNotFoundError(f"grant not found: {grant_id}")
                    grant = Grant.model_validate(row[0])
                    consumed_at, revoked_at = row[1], row[2]
                    if revoked_at is not None or grant.revoked_at is not None:
                        raise GrantAlreadyConsumedError(f"grant revoked: {grant_id}")
                    if consumed_at is not None or grant.consumed_at is not None:
                        raise GrantAlreadyConsumedError(f"grant already consumed: {grant_id}")
                    updated = grant.model_copy(update={"consumed_at": _utc_now()})
                    updated = updated.model_copy(update={"grant_hash": grant_hash(updated)})
                    conn.execute(
                        """
                        UPDATE enterprise.grants
                        SET payload = %s::jsonb, consumed_at = NOW()
                        WHERE tenant_id = %s AND run_id = %s AND grant_id = %s
                        """,
                        (
                            updated.model_dump_json(),
                            tenant,
                            run_id,
                            grant_id,
                        ),
                    )
            except SerializationFailure:
                continue
            assert_tenant_match(tenant, updated.tenant_id, operation="consume_grant")
            return updated
        raise GrantAlreadyConsumedError(f"grant already consumed: {grant_id}")

    def validate_approved_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        action: Action,
        policy_snapshot_id: str,
        target: dict[str, str],
    ) -> tuple[ApprovalRequest, Grant]:
        tenant = validate_tenant_id(tenant_id)
        request = self.load_request(tenant_id=tenant, run_id=run_id, request_id=request_id)
        if request.status != "approved":
            raise PermissionError(f"approval request is not approved: {request_id}")
        expected = (tenant, action, policy_snapshot_id, target)
        actual = (request.tenant_id, request.action, request.policy_snapshot_id, request.target)
        if actual != expected:
            raise PermissionError(f"approval request binding mismatch: {request_id}")
        grant = self.load_grant(
            tenant_id=tenant, run_id=run_id, grant_id=grant_id_for_request(request)
        )
        grant_binding = (grant.tenant_id, grant.action, grant.policy_snapshot_id, grant.target)
        if grant.request_id != request.request_id or grant_binding != expected:
            raise PermissionError(f"approval grant binding mismatch: {grant.grant_id}")
        if grant.revoked_at is not None or grant.consumed_at is not None:
            raise GrantAlreadyConsumedError(f"approval grant unavailable: {grant.grant_id}")
        return request, grant

    def consume_approved_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        action: Action,
        policy_snapshot_id: str,
        target: dict[str, str],
    ) -> Grant:
        _, grant = self.validate_approved_request(
            tenant_id=tenant_id,
            run_id=run_id,
            request_id=request_id,
            action=action,
            policy_snapshot_id=policy_snapshot_id,
            target=target,
        )
        return self.consume_grant(tenant_id=tenant_id, run_id=run_id, grant_id=grant.grant_id)


class PostgresAuditStore:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def emit(
        self,
        kind: AuditEventKind,
        *,
        tenant_id: str,
        run_id: str,
        actor_id: str,
        payload: dict[str, str] | None = None,
        status: str = "success",
        message: str | None = None,
    ) -> AuditEvent:
        tenant = validate_tenant_id(tenant_id)
        with self._uow.transaction() as conn:
            event = pg_audit.emit_audit_event(
                conn,
                kind,
                tenant_id=tenant,
                run_id=run_id,
                actor_id=actor_id,
                payload=payload,
                status=status,
                message=message,
            )
        return event

    def verify_integrity(self) -> tuple[bool, str]:
        with self._uow.connection() as conn:
            return pg_audit.verify_audit_chain(conn)

    def list_events(self, *, tenant_id: str, run_id: str | None = None) -> list[AuditEvent]:
        tenant = validate_tenant_id(tenant_id)
        with self._uow.connection() as conn:
            return pg_audit.list_audit_events(conn, tenant_id=tenant, run_id=run_id)

    def tamper_first_event_for_test(self) -> None:
        with self._uow.connection() as conn:
            pg_audit.tamper_first_audit_event(conn)
            conn.commit()


class PostgresEvalResultStore:
    def __init__(self, uow: UnitOfWork, artifacts_root: Path) -> None:
        self._uow = uow
        self._artifacts_root = artifacts_root

    def write_results(
        self, *, tenant_id: str, run_id: str, results: list[EvaluationResult]
    ) -> Path:
        tenant = validate_tenant_id(tenant_id)
        path = self._artifacts_root / "enterprise" / "eval" / "results" / run_id / "results.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([item.model_dump(mode="json") for item in results], indent=2),
            encoding="utf-8",
        )
        with self._uow.connection() as conn:
            conn.execute(
                """
                INSERT INTO enterprise.eval_results (tenant_id, run_id, results, written_at)
                VALUES (%s, %s, %s::jsonb, NOW())
                ON CONFLICT (tenant_id, run_id) DO UPDATE
                SET results = EXCLUDED.results, written_at = NOW()
                """,
                (
                    tenant,
                    run_id,
                    json.dumps([item.model_dump(mode="json") for item in results]),
                ),
            )
            conn.commit()
        return path

    def read_results(self, *, tenant_id: str, run_id: str) -> list[EvaluationResult]:
        tenant = validate_tenant_id(tenant_id)
        with self._uow.connection() as conn:
            row = conn.execute(
                """
                SELECT results FROM enterprise.eval_results
                WHERE tenant_id = %s AND run_id = %s
                """,
                (tenant, run_id),
            ).fetchone()
        if row is None:
            return []
        payload = row[0]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return [EvaluationResult.model_validate(item) for item in payload]


class PostgresTraceStore:
    def __init__(self, uow: UnitOfWork, artifacts_root: Path) -> None:
        self._uow = uow
        self._artifacts_root = artifacts_root

    def emit_event(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_type: TraceEventType | str,
        node_id: str,
        seq: int,
        payload: dict[str, object] | None = None,
        actor_id: str | None = None,
        policy_snapshot_id: str | None = None,
        cost: NodeCost | None = None,
        duration_ms: int | None = None,
        event_id: str | None = None,
        timestamp: str | None = None,
    ) -> TraceEvent | None:
        tenant = validate_tenant_id(tenant_id)
        emitter = TraceEmitter(self._artifacts_root, run_id)
        event = emitter.emit(
            event_type,
            node_id=node_id,
            seq=seq,
            tenant_id=tenant,
            payload=payload,
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            cost=cost,
            duration_ms=duration_ms,
            event_id=event_id,
            timestamp=timestamp,
        )
        if event is None:
            return None
        with self._uow.connection() as conn:
            conn.execute(
                """
                INSERT INTO enterprise.trace_events (tenant_id, run_id, event_id, seq, payload)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (tenant_id, run_id, event_id) DO NOTHING
                """,
                (
                    tenant,
                    run_id,
                    event.event_id,
                    event.seq,
                    event.model_dump_json(),
                ),
            )
            conn.commit()
        return event

    def list_events(self, *, tenant_id: str, run_id: str) -> list[TraceEvent]:
        tenant = validate_tenant_id(tenant_id)
        with self._uow.connection() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM enterprise.trace_events
                WHERE tenant_id = %s AND run_id = %s
                ORDER BY seq ASC
                """,
                (tenant, run_id),
            ).fetchall()
        if rows:
            return [TraceEvent.model_validate(row[0]) for row in rows]
        return [
            item
            for item in TraceEmitter(self._artifacts_root, run_id).iter_events()
            if item.tenant_id == tenant
        ]

    def write_timeline(self, *, tenant_id: str, run_id: str) -> Path:
        validate_tenant_id(tenant_id)
        return write_timeline(self._artifacts_root, run_id)


class PostgresEvidenceStore:
    def __init__(self, uow: UnitOfWork, artifacts_root: Path, runs: PostgresRunStore, audit: PostgresAuditStore, approvals: PostgresApprovalStore, trace: PostgresTraceStore) -> None:
        self._uow = uow
        self._artifacts_root = artifacts_root
        self._runs = runs
        self._audit = audit
        self._approvals = approvals
        self._trace = trace

    def export_run_evidence(self, *, tenant_id: str, run_id: str) -> Path:
        tenant = validate_tenant_id(tenant_id)
        checkpoint = self._runs.load_checkpoint(tenant_id=tenant, run_id=run_id)
        approvals = [
            item.model_dump(mode="json")
            for item in self._approvals.list_requests(tenant_id=tenant, run_id=run_id)
        ]
        audit_events = self._audit.list_events(tenant_id=tenant, run_id=run_id)
        trace_events = self._trace.list_events(tenant_id=tenant, run_id=run_id)
        trace_lines = [
            json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            for item in trace_events
        ]
        with self._uow.connection() as conn:
            path = export_run_evidence_from_pg(
                conn,
                self._artifacts_root,
                tenant_id=tenant,
                run_id=run_id,
                checkpoint=checkpoint,
                approvals=approvals,
                audit_events=audit_events,
                trace_lines=trace_lines,
            )
            conn.commit()
        return path


@dataclass(frozen=True)
class PostgresBackend:
    pool: ConnectionPool
    artifacts_root: Path
    _uow: UnitOfWork

    @classmethod
    def connect(cls, dsn: str, artifacts_root: Path) -> PostgresBackend:
        pool = ConnectionPool(dsn, min_size=1, max_size=5, open=True)
        apply_migrations(pool)
        uow = UnitOfWork(pool)
        backend = cls(pool=pool, artifacts_root=artifacts_root, _uow=uow)
        return backend

    def close(self) -> None:
        self.pool.close()

    @property
    def runs(self) -> PostgresRunStore:
        return PostgresRunStore(self._uow, self.artifacts_root)

    @property
    def approvals(self) -> PostgresApprovalStore:
        return PostgresApprovalStore(self._uow, self.artifacts_root)

    @property
    def audit(self) -> PostgresAuditStore:
        return PostgresAuditStore(self._uow)

    @property
    def eval_results(self) -> PostgresEvalResultStore:
        return PostgresEvalResultStore(self._uow, self.artifacts_root)

    @property
    def trace(self) -> PostgresTraceStore:
        return PostgresTraceStore(self._uow, self.artifacts_root)

    @property
    def evidence(self) -> PostgresEvidenceStore:
        return PostgresEvidenceStore(
            self._uow,
            self.artifacts_root,
            self.runs,
            self.audit,
            self.approvals,
            self.trace,
        )

    @property
    def commands(self) -> PostgresCommandQueue:
        return PostgresCommandQueue(self._uow)

    @property
    def leases(self) -> PostgresRunLeaseStore:
        return PostgresRunLeaseStore(self._uow)

    @property
    def webhooks(self) -> PostgresWebhookEventStore:
        return PostgresWebhookEventStore(self._uow)

    def probe(self) -> bool:
        return self._uow.probe()
