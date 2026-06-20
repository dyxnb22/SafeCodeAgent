"""Background lease heartbeat for long-running worker jobs (R8)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from safecode.enterprise.worker.lease import RunLeaseStore


class LeaseOwnershipLostError(Exception):
    """Raised when a worker loses lease ownership before finishing a job."""


@dataclass
class LeaseHeartbeatGuard:
    """Periodically refresh an active run lease until stopped."""

    leases: RunLeaseStore
    tenant_id: str
    run_id: str
    worker_id: str
    fence_token: str
    ttl_seconds: int

    def __post_init__(self) -> None:
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread: threading.Thread | None = None
        self._heartbeat_error: Exception | None = None

    def start(self) -> None:
        interval = max(1, self.ttl_seconds // 3)
        self._thread = threading.Thread(
            target=self._run,
            args=(interval,),
            name=f"lease-heartbeat-{self.run_id}",
            daemon=True,
        )
        self._thread.start()

    def _run(self, interval: float) -> None:
        while not self._stop.wait(interval):
            try:
                if not self.leases.heartbeat(
                    tenant_id=self.tenant_id,
                    run_id=self.run_id,
                    worker_id=self.worker_id,
                    ttl_seconds=self.ttl_seconds,
                    fence_token=self.fence_token,
                ):
                    self._lost.set()
                    return
            except Exception as exc:  # pragma: no cover - surfaced via ownership_lost
                self._heartbeat_error = exc
                self._lost.set()
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                self._thread = None

    def ownership_lost(self) -> bool:
        return self._lost.is_set()

    def heartbeat_error(self) -> Exception | None:
        return self._heartbeat_error
