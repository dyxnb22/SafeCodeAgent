"""Webhook delivery persistence for idempotent GitHub ingest (v2.2.1-T2)."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from safecode.enterprise.persistence.protocols import validate_tenant_id


class WebhookDeliveryConflictError(Exception):
    """Raised when the same delivery id maps to a different run."""


class WebhookDeliveryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    delivery_id: str
    tenant_id: str
    event_type: str
    run_id: str
    idempotency_key: str
    payload_digest: str
    created_at: str


@runtime_checkable
class WebhookEventStore(Protocol):
    def get_delivery(self, *, delivery_id: str) -> WebhookDeliveryRecord | None: ...

    def record_delivery(
        self,
        *,
        delivery_id: str,
        tenant_id: str,
        event_type: str,
        run_id: str,
        idempotency_key: str,
        payload_digest: str,
    ) -> WebhookDeliveryRecord: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def payload_digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _validate_delivery_id(delivery_id: str) -> str:
    normalized = delivery_id.strip()
    if len(normalized) < 8 or len(normalized) > 128:
        raise ValueError("delivery id must be between 8 and 128 characters")
    return normalized


def _events_root(sac_root: Path) -> Path:
    return sac_root / "enterprise" / "webhooks"


def _delivery_path(sac_root: Path, delivery_id: str) -> Path:
    digest = hashlib.sha256(delivery_id.encode("utf-8")).hexdigest()[:32]
    return _events_root(sac_root) / f"{digest}.json"


def _atomic_write_json(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class LocalWebhookEventStore:
    sac_root: Path

    def get_delivery(self, *, delivery_id: str) -> WebhookDeliveryRecord | None:
        path = _delivery_path(self.sac_root, _validate_delivery_id(delivery_id))
        if not path.is_file():
            return None
        return WebhookDeliveryRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def record_delivery(
        self,
        *,
        delivery_id: str,
        tenant_id: str,
        event_type: str,
        run_id: str,
        idempotency_key: str,
        payload_digest: str,
    ) -> WebhookDeliveryRecord:
        delivery = _validate_delivery_id(delivery_id)
        tenant = validate_tenant_id(tenant_id)
        existing = self.get_delivery(delivery_id=delivery)
        if existing is not None:
            if (
                existing.run_id != run_id
                or existing.idempotency_key != idempotency_key
                or existing.tenant_id != tenant
            ):
                raise WebhookDeliveryConflictError(
                    f"delivery id {delivery!r} already bound to another run"
                )
            return existing
        record = WebhookDeliveryRecord(
            delivery_id=delivery,
            tenant_id=tenant,
            event_type=event_type,
            run_id=run_id,
            idempotency_key=idempotency_key,
            payload_digest=payload_digest,
            created_at=_utc_now(),
        )
        _atomic_write_json(
            _delivery_path(self.sac_root, delivery),
            record.model_dump(),
        )
        return record


@dataclass(frozen=True)
class PostgresWebhookEventStore:
    uow: object

    def get_delivery(self, *, delivery_id: str) -> WebhookDeliveryRecord | None:
        from safecode.enterprise.persistence.postgres.unit_of_work import UnitOfWork

        if not isinstance(self.uow, UnitOfWork):
            raise TypeError("postgres webhook store requires UnitOfWork")
        delivery = _validate_delivery_id(delivery_id)
        with self.uow.connection() as conn:
            row = conn.execute(
                """
                SELECT delivery_id, tenant_id, event_type, run_id, idempotency_key, payload_digest, created_at
                FROM enterprise.webhook_events
                WHERE delivery_id = %s
                """,
                (delivery,),
            ).fetchone()
        if row is None:
            return None
        return WebhookDeliveryRecord(
            delivery_id=str(row[0]),
            tenant_id=str(row[1]),
            event_type=str(row[2]),
            run_id=str(row[3]),
            idempotency_key=str(row[4]),
            payload_digest=str(row[5]),
            created_at=row[6].isoformat().replace("+00:00", "+00:00"),
        )

    def record_delivery(
        self,
        *,
        delivery_id: str,
        tenant_id: str,
        event_type: str,
        run_id: str,
        idempotency_key: str,
        payload_digest: str,
    ) -> WebhookDeliveryRecord:
        from safecode.enterprise.persistence.postgres.unit_of_work import UnitOfWork

        if not isinstance(self.uow, UnitOfWork):
            raise TypeError("postgres webhook store requires UnitOfWork")
        delivery = _validate_delivery_id(delivery_id)
        tenant = validate_tenant_id(tenant_id)
        existing = self.get_delivery(delivery_id=delivery)
        if existing is not None:
            if (
                existing.run_id != run_id
                or existing.idempotency_key != idempotency_key
                or existing.tenant_id != tenant
            ):
                raise WebhookDeliveryConflictError(
                    f"delivery id {delivery!r} already bound to another run"
                )
            return existing
        record = WebhookDeliveryRecord(
            delivery_id=delivery,
            tenant_id=tenant,
            event_type=event_type,
            run_id=run_id,
            idempotency_key=idempotency_key,
            payload_digest=payload_digest,
            created_at=_utc_now(),
        )
        with self.uow.connection() as conn:
            conn.execute(
                """
                INSERT INTO enterprise.webhook_events (
                    delivery_id, tenant_id, event_type, run_id, idempotency_key, payload_digest, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    record.delivery_id,
                    record.tenant_id,
                    record.event_type,
                    record.run_id,
                    record.idempotency_key,
                    record.payload_digest,
                ),
            )
            conn.commit()
        return record
