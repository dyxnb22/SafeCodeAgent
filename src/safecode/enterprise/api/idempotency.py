"""API idempotency persistence for approval commands (R8)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.worker.queue import IdempotencyConflictError, _validate_idempotency_key
from safecode.utils.file_lock import atomic_replace_text, keyed_exclusive_lock, lock_path_for

ApprovalApiOperation = Literal["decide", "revoke"]


class ApprovalIdempotencyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str
    idempotency_key: str
    operation: ApprovalApiOperation
    request_fingerprint: str
    response: dict[str, str] = Field(default_factory=dict)
    created_at: str


def approval_request_fingerprint(
    *,
    operation: ApprovalApiOperation,
    approval_id: str,
    decision: str | None = None,
    rationale: str = "",
    actor_id: str = "",
) -> str:
    payload = {
        "operation": operation,
        "approval_id": approval_id,
        "decision": decision or "",
        "rationale": rationale,
        "actor_id": actor_id,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest


def approval_resume_idempotency_key(*, tenant_id: str, approval_id: str, decision: str) -> str:
    tenant = validate_tenant_id(tenant_id)
    digest = hashlib.sha256(f"{tenant}:{approval_id}:{decision}".encode("utf-8")).hexdigest()[:60]
    return f"apr-{digest}"


@runtime_checkable
class ApiIdempotencyStore(Protocol):
    def get(
        self, *, tenant_id: str, idempotency_key: str
    ) -> ApprovalIdempotencyRecord | None: ...

    def save(self, record: ApprovalIdempotencyRecord) -> ApprovalIdempotencyRecord: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _record_path(sac_root: Path, tenant_id: str, idempotency_key: str) -> Path:
    tenant = validate_tenant_id(tenant_id)
    key = _validate_idempotency_key(idempotency_key)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return sac_root / "enterprise" / "api_idempotency" / tenant / f"{digest}.json"


@dataclass(frozen=True)
class LocalApiIdempotencyStore:
    sac_root: Path

    def get(
        self, *, tenant_id: str, idempotency_key: str
    ) -> ApprovalIdempotencyRecord | None:
        path = _record_path(self.sac_root, tenant_id, idempotency_key)
        if not path.is_file():
            return None
        return ApprovalIdempotencyRecord.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )

    def save(self, record: ApprovalIdempotencyRecord) -> ApprovalIdempotencyRecord:
        tenant = validate_tenant_id(record.tenant_id)
        path = _record_path(self.sac_root, tenant, record.idempotency_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with keyed_exclusive_lock(str(path.resolve()), lock_path_for(path)):
            existing = self.get(tenant_id=tenant, idempotency_key=record.idempotency_key)
            if existing is not None:
                if existing.request_fingerprint != record.request_fingerprint:
                    raise IdempotencyConflictError(
                        f"idempotency key {record.idempotency_key!r} already bound to another request"
                    )
                return existing
            atomic_replace_text(path, record.model_dump_json())
        return record


@dataclass(frozen=True)
class PostgresApiIdempotencyStore:
    uow: object

    def get(
        self, *, tenant_id: str, idempotency_key: str
    ) -> ApprovalIdempotencyRecord | None:
        tenant = validate_tenant_id(tenant_id)
        key = _validate_idempotency_key(idempotency_key)
        with self.uow.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                """
                SELECT tenant_id, idempotency_key, operation, request_fingerprint, response, created_at
                FROM enterprise.api_idempotency
                WHERE tenant_id = %s AND idempotency_key = %s
                """,
                (tenant, key),
            ).fetchone()
        if row is None:
            return None
        return ApprovalIdempotencyRecord(
            tenant_id=str(row[0]),
            idempotency_key=str(row[1]),
            operation=row[2],  # type: ignore[arg-type]
            request_fingerprint=str(row[3]),
            response=dict(row[4] or {}),
            created_at=row[5].isoformat().replace("+00:00", "+00:00"),
        )

    def save(self, record: ApprovalIdempotencyRecord) -> ApprovalIdempotencyRecord:
        tenant = validate_tenant_id(record.tenant_id)
        key = _validate_idempotency_key(record.idempotency_key)
        existing = self.get(tenant_id=tenant, idempotency_key=key)
        if existing is not None:
            if existing.request_fingerprint != record.request_fingerprint:
                raise IdempotencyConflictError(
                    f"idempotency key {key!r} already bound to another request"
                )
            return existing
        created_at = record.created_at or _utc_now()
        with self.uow.connection() as conn:  # type: ignore[attr-defined]
            conn.execute(
                """
                INSERT INTO enterprise.api_idempotency (
                    tenant_id, idempotency_key, operation, request_fingerprint, response, created_at
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                """,
                (
                    tenant,
                    key,
                    record.operation,
                    record.request_fingerprint,
                    json.dumps(record.response),
                    created_at,
                ),
            )
            conn.commit()
        stored = self.get(tenant_id=tenant, idempotency_key=key)
        if stored is None:
            raise RuntimeError("failed to persist api idempotency record")
        if stored.request_fingerprint != record.request_fingerprint:
            raise IdempotencyConflictError(
                f"idempotency key {key!r} already bound to another request"
            )
        return stored


def api_idempotency_for(backend: object) -> ApiIdempotencyStore:
    store = getattr(backend, "api_idempotency", None)
    if store is not None:
        return store
    sac_root = getattr(backend, "sac_root", None)
    if sac_root is not None:
        return LocalApiIdempotencyStore(sac_root)
    uow = getattr(backend, "_uow", None)
    artifacts_root = getattr(backend, "artifacts_root", None)
    if uow is not None and artifacts_root is not None:
        return PostgresApiIdempotencyStore(uow)
    raise TypeError("backend does not expose an API idempotency store")
