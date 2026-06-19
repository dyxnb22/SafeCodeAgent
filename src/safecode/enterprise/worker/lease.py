"""Run lease persistence for worker coordination (v2.1.5-T3)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.workflow.ids import validate_run_id


class LeaseHeldError(Exception):
    """Raised when a run lease is held by another worker."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _lease_root(sac_root: Path) -> Path:
    return sac_root / "enterprise" / "worker" / "leases"


def _lease_path(sac_root: Path, tenant_id: str, run_id: str) -> Path:
    return _lease_root(sac_root) / validate_tenant_id(tenant_id) / f"{validate_run_id(run_id)}.json"


@runtime_checkable
class RunLeaseStore(Protocol):
    def acquire(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool: ...

    def heartbeat(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool: ...

    def release(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
    ) -> None: ...


@dataclass(frozen=True)
class LocalRunLeaseStore:
    sac_root: Path

    def _read(self, tenant_id: str, run_id: str) -> dict[str, str] | None:
        path = _lease_path(self.sac_root, tenant_id, run_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, tenant_id: str, run_id: str, payload: dict[str, str]) -> None:
        path = _lease_path(self.sac_root, tenant_id, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)

    def acquire(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        now = _utc_now()
        existing = self._read(tenant, run_id)
        if existing is not None:
            expires = datetime.fromisoformat(existing["expires_at"])
            if existing["worker_id"] != worker_id and expires > now:
                return False
        expires_at = (now + timedelta(seconds=max(1, ttl_seconds))).isoformat()
        self._write(
            tenant,
            run_id,
            {
                "tenant_id": tenant,
                "run_id": run_id,
                "worker_id": worker_id,
                "expires_at": expires_at,
                "heartbeat_at": now.isoformat(),
            },
        )
        return True

    def heartbeat(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        existing = self._read(tenant, run_id)
        if existing is None or existing["worker_id"] != worker_id:
            return False
        now = _utc_now()
        self._write(
            tenant,
            run_id,
            {
                **existing,
                "expires_at": (now + timedelta(seconds=max(1, ttl_seconds))).isoformat(),
                "heartbeat_at": now.isoformat(),
            },
        )
        return True

    def release(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
    ) -> None:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        path = _lease_path(self.sac_root, tenant, run_id)
        existing = self._read(tenant, run_id)
        if existing is None:
            return
        if existing["worker_id"] != worker_id:
            raise LeaseHeldError(f"lease held by {existing['worker_id']!r}")
        if path.is_file():
            path.unlink()


@dataclass(frozen=True)
class PostgresRunLeaseStore:
    uow: object

    def acquire(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        ttl = max(1, ttl_seconds)
        with self.uow.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                """
                SELECT worker_id, expires_at
                FROM enterprise.run_leases
                WHERE tenant_id = %s AND run_id = %s
                FOR UPDATE
                """,
                (tenant, run_id),
            ).fetchone()
            now = _utc_now()
            if row is not None and row[0] != worker_id and row[1] > now:
                conn.commit()
                return False
            conn.execute(
                """
                INSERT INTO enterprise.run_leases (
                    tenant_id, run_id, worker_id, expires_at, heartbeat_at
                ) VALUES (%s, %s, %s, NOW() + (%s || ' seconds')::interval, NOW())
                ON CONFLICT (tenant_id, run_id) DO UPDATE SET
                    worker_id = EXCLUDED.worker_id,
                    expires_at = EXCLUDED.expires_at,
                    heartbeat_at = EXCLUDED.heartbeat_at
                WHERE enterprise.run_leases.worker_id = EXCLUDED.worker_id
                   OR enterprise.run_leases.expires_at <= NOW()
                """,
                (tenant, run_id, worker_id, str(ttl)),
            )
            conn.commit()
        return True

    def heartbeat(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        ttl = max(1, ttl_seconds)
        with self.uow.connection() as conn:  # type: ignore[attr-defined]
            updated = conn.execute(
                """
                UPDATE enterprise.run_leases
                SET expires_at = NOW() + (%s || ' seconds')::interval,
                    heartbeat_at = NOW()
                WHERE tenant_id = %s AND run_id = %s AND worker_id = %s
                """,
                (str(ttl), tenant, run_id, worker_id),
            ).rowcount
            conn.commit()
        return bool(updated)

    def release(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
    ) -> None:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        with self.uow.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                """
                SELECT worker_id FROM enterprise.run_leases
                WHERE tenant_id = %s AND run_id = %s
                """,
                (tenant, run_id),
            ).fetchone()
            if row is None:
                conn.commit()
                return
            if row[0] != worker_id:
                raise LeaseHeldError(f"lease held by {row[0]!r}")
            conn.execute(
                "DELETE FROM enterprise.run_leases WHERE tenant_id = %s AND run_id = %s",
                (tenant, run_id),
            )
            conn.commit()
