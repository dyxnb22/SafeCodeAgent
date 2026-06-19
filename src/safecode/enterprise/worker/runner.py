"""Durable worker runner with lease-guarded execution (v2.1.5-T3)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.persistence.postgres.backend import PostgresBackend
from safecode.enterprise.worker.lease import LocalRunLeaseStore, RunLeaseStore
from safecode.enterprise.worker.models import QueueJob
from safecode.enterprise.worker.queue import CommandQueue, LocalCommandQueue
from safecode.enterprise.worker.status import is_terminal
from safecode.enterprise.workflow.exceptions import WorkflowInterrupted
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator
from safecode.enterprise.workflow.types import WorkflowStatus


PersistenceBackend = LocalBackend | PostgresBackend


def _artifacts_root(backend: PersistenceBackend) -> Path:
    if isinstance(backend, LocalBackend):
        return backend.sac_root
    return backend.artifacts_root


def lease_store_for(backend: PersistenceBackend) -> RunLeaseStore:
    store = getattr(backend, "leases", None)
    if store is not None:
        return store
    return LocalRunLeaseStore(_artifacts_root(backend))


def command_queue_for_backend(backend: PersistenceBackend) -> CommandQueue:
    queue = getattr(backend, "commands", None)
    if queue is not None:
        return queue
    return LocalCommandQueue(_artifacts_root(backend))


@dataclass(frozen=True)
class WorkerRunner:
    backend: PersistenceBackend
    worker_id: str
    project_root: Path
    lease_ttl_seconds: int = 30

    @property
    def queue(self) -> CommandQueue:
        return command_queue_for_backend(self.backend)

    @property
    def leases(self) -> RunLeaseStore:
        return lease_store_for(self.backend)

    def process_once(self) -> bool:
        job = self.queue.poll_pending_job()
        if job is None:
            return False
        if not self.leases.acquire(
            tenant_id=job.tenant_id,
            run_id=job.run_id,
            worker_id=self.worker_id,
            ttl_seconds=self.lease_ttl_seconds,
        ):
            self._requeue(job)
            return False
        try:
            self._execute(job)
            self.queue.complete_job(job.job_id)
        except Exception as exc:
            self.queue.fail_job(job.job_id, message=str(exc))
        finally:
            self.leases.release(
                tenant_id=job.tenant_id,
                run_id=job.run_id,
                worker_id=self.worker_id,
            )
        return True

    def _requeue(self, job: QueueJob) -> None:
        self.queue.enqueue_job(
            tenant_id=job.tenant_id,
            run_id=job.run_id,
            command=job.command,
            payload=job.payload,
        )

    def _execute(self, job: QueueJob) -> None:
        checkpoint = self.backend.runs.load_checkpoint(
            tenant_id=job.tenant_id, run_id=job.run_id
        )
        if is_terminal(checkpoint.state.status):
            return
        if checkpoint.state.status is WorkflowStatus.cancelled:
            return
        orchestrator = LocalOrchestrator(
            _artifacts_root(self.backend),
            runtime="local",
            backend=self.backend,
        )
        if job.command == "start":
            try:
                asyncio.run(orchestrator.run(checkpoint.state))
            except WorkflowInterrupted:
                return
            return
        if job.command == "resume":
            try:
                asyncio.run(orchestrator.resume(job.run_id, tenant_id=job.tenant_id))
            except WorkflowInterrupted:
                return
            return
        if job.command == "cancel":
            return
        raise ValueError(f"unsupported queue command: {job.command}")

    def heartbeat_active_leases(self) -> int:
        root = _artifacts_root(self.backend) / "enterprise" / "worker" / "leases"
        if not root.is_dir():
            return 0
        refreshed = 0
        for tenant_dir in root.iterdir():
            if not tenant_dir.is_dir():
                continue
            for lease_file in tenant_dir.glob("*.json"):
                run_id = lease_file.stem
                if self.leases.heartbeat(
                    tenant_id=tenant_dir.name,
                    run_id=run_id,
                    worker_id=self.worker_id,
                    ttl_seconds=self.lease_ttl_seconds,
                ):
                    refreshed += 1
        return refreshed
