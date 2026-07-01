"""Run lease persistence for worker coordination (v2.1.5-T3).

中文模块说明：worker 对 run 的租约、心跳与 fence_token，防止并发双执行。
- 架构位置：Workflow 平面；runner 执行前 acquire，完成后带 fence 释放。
- 安全不变量：过期租约可被抢占；fence 不匹配则拒绝完成，避免 TOCTOU。
- 学习路径：读 ``worker/runner.py`` 与 R8 concurrency 测试。
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from safecode.enterprise.persistence.protocols import validate_tenant_id
from safecode.enterprise.workflow.ids import validate_run_id
from safecode.utils.file_lock import atomic_replace_text, keyed_exclusive_lock, lock_path_for


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
        fence_token: str = "",
    ) -> bool: ...

    def holds_lease(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        fence_token: str,
    ) -> bool: ...

    def read_fence_token(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
    ) -> str | None: ...

    def execute_if_owned(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        fence_token: str,
        operation: Callable[[], None],
    ) -> bool: ...

    def release(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        fence_token: str = "",
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
        atomic_replace_text(path, json.dumps(payload, sort_keys=True))

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
        path = _lease_path(self.sac_root, tenant, run_id)
        with keyed_exclusive_lock(f"lease:{tenant}:{run_id}", lock_path_for(path)):
            now = _utc_now()
            existing = self._read(tenant, run_id)
            if existing is not None:
                expires = datetime.fromisoformat(existing["expires_at"])
                if existing["worker_id"] != worker_id and expires > now:
                    return False
            fence_token = secrets.token_hex(8)
            expires_at = (now + timedelta(seconds=max(1, ttl_seconds))).isoformat()
            payload = {
                "tenant_id": tenant,
                "run_id": run_id,
                "worker_id": worker_id,
                "expires_at": expires_at,
                "heartbeat_at": now.isoformat(),
                "fence_token": fence_token,
            }
            atomic_replace_text(path, json.dumps(payload, sort_keys=True))
            verified = self._read(tenant, run_id)
            return verified is not None and verified["worker_id"] == worker_id

    def read_fence_token(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
    ) -> str | None:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        existing = self._read(tenant, run_id)
        if existing is None or existing.get("worker_id") != worker_id:
            return None
        return str(existing.get("fence_token", ""))

    def holds_lease(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        fence_token: str,
    ) -> bool:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        existing = self._read(tenant, run_id)
        if existing is None:
            return False
        if existing.get("worker_id") != worker_id:
            return False
        if str(existing.get("fence_token", "")) != fence_token:
            return False
        expires = datetime.fromisoformat(existing["expires_at"])
        return expires > _utc_now()

    def heartbeat(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        ttl_seconds: int,
        fence_token: str = "",
    ) -> bool:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        path = _lease_path(self.sac_root, tenant, run_id)
        with keyed_exclusive_lock(f"lease:{tenant}:{run_id}", lock_path_for(path)):
            existing = self._read(tenant, run_id)
            if existing is None or existing["worker_id"] != worker_id:
                return False
            if fence_token and str(existing.get("fence_token", "")) != fence_token:
                return False
            now = _utc_now()
            payload = {
                **existing,
                "expires_at": (now + timedelta(seconds=max(1, ttl_seconds))).isoformat(),
                "heartbeat_at": now.isoformat(),
            }
            atomic_replace_text(path, json.dumps(payload, sort_keys=True))
        return True

    def execute_if_owned(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        fence_token: str,
        operation: Callable[[], None],
    ) -> bool:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        path = _lease_path(self.sac_root, tenant, run_id)
        with keyed_exclusive_lock(f"lease:{tenant}:{run_id}", lock_path_for(path)):
            existing = self._read(tenant, run_id)
            if existing is None:
                return False
            if existing.get("worker_id") != worker_id:
                return False
            if str(existing.get("fence_token", "")) != fence_token:
                return False
            if datetime.fromisoformat(existing["expires_at"]) <= _utc_now():
                return False
            operation()
            return True

    def release(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        fence_token: str = "",
    ) -> None:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        path = _lease_path(self.sac_root, tenant, run_id)
        with keyed_exclusive_lock(f"lease:{tenant}:{run_id}", lock_path_for(path)):
            existing = self._read(tenant, run_id)
            if existing is None:
                return
            if existing["worker_id"] != worker_id:
                raise LeaseHeldError(f"lease held by {existing['worker_id']!r}")
            if fence_token and str(existing.get("fence_token", "")) != fence_token:
                raise LeaseHeldError("lease fence token no longer belongs to this execution")
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
        fence_token = secrets.token_hex(8)
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
                    tenant_id, run_id, worker_id, expires_at, heartbeat_at, fence_token
                ) VALUES (%s, %s, %s, NOW() + (%s || ' seconds')::interval, NOW(), %s)
                ON CONFLICT (tenant_id, run_id) DO UPDATE SET
                    worker_id = EXCLUDED.worker_id,
                    expires_at = EXCLUDED.expires_at,
                    heartbeat_at = EXCLUDED.heartbeat_at,
                    fence_token = EXCLUDED.fence_token
                WHERE enterprise.run_leases.worker_id = EXCLUDED.worker_id
                   OR enterprise.run_leases.expires_at <= NOW()
                """,
                (tenant, run_id, worker_id, str(ttl), fence_token),
            )
            conn.commit()
        return True

    def read_fence_token(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
    ) -> str | None:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        with self.uow.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                """
                SELECT worker_id, fence_token
                FROM enterprise.run_leases
                WHERE tenant_id = %s AND run_id = %s
                """,
                (tenant, run_id),
            ).fetchone()
        if row is None or row[0] != worker_id:
            return None
        return str(row[1] or "")

    def holds_lease(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        fence_token: str,
    ) -> bool:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        with self.uow.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                """
                SELECT worker_id, fence_token, expires_at
                FROM enterprise.run_leases
                WHERE tenant_id = %s AND run_id = %s
                """,
                (tenant, run_id),
            ).fetchone()
        if row is None:
            return False
        if row[0] != worker_id:
            return False
        if str(row[1] or "") != fence_token:
            return False
        return row[2] > _utc_now()

    def heartbeat(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        ttl_seconds: int,
        fence_token: str = "",
    ) -> bool:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        ttl = max(1, ttl_seconds)
        with self.uow.connection() as conn:  # type: ignore[attr-defined]
            if fence_token:
                updated = conn.execute(
                    """
                    UPDATE enterprise.run_leases
                    SET expires_at = NOW() + (%s || ' seconds')::interval,
                        heartbeat_at = NOW()
                    WHERE tenant_id = %s AND run_id = %s AND worker_id = %s
                      AND fence_token = %s
                    """,
                    (str(ttl), tenant, run_id, worker_id, fence_token),
                ).rowcount
            else:
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

    def execute_if_owned(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        fence_token: str,
        operation: Callable[[], None],
    ) -> bool:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        with self.uow.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                """
                SELECT worker_id, fence_token, expires_at > NOW()
                FROM enterprise.run_leases
                WHERE tenant_id = %s AND run_id = %s
                FOR UPDATE
                """,
                (tenant, run_id),
            ).fetchone()
            if (
                row is None
                or row[0] != worker_id
                or str(row[1] or "") != fence_token
                or not bool(row[2])
            ):
                conn.rollback()
                return False
            operation()
            conn.commit()
            return True

    def release(
        self,
        *,
        tenant_id: str,
        run_id: str,
        worker_id: str,
        fence_token: str = "",
    ) -> None:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        with self.uow.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                """
                SELECT worker_id, fence_token FROM enterprise.run_leases
                WHERE tenant_id = %s AND run_id = %s
                """,
                (tenant, run_id),
            ).fetchone()
            if row is None:
                conn.commit()
                return
            if row[0] != worker_id:
                raise LeaseHeldError(f"lease held by {row[0]!r}")
            if fence_token and str(row[1] or "") != fence_token:
                raise LeaseHeldError("lease fence token no longer belongs to this execution")
            conn.execute(
                "DELETE FROM enterprise.run_leases WHERE tenant_id = %s AND run_id = %s",
                (tenant, run_id),
            )
            conn.commit()
