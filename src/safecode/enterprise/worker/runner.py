"""持久化 Worker 执行器：租约保护下的命令队列消费（v2.1.5-T3）。

执行流程（``process_once``）：
1. ``poll_pending_job`` 从队列取待处理任务
2. ``leases.acquire`` 获取 run 级租约（默认 TTL 30s），失败则重新入队
3. 按 command 调用编排器：start → run，resume → resume，cancel → 无操作
4. 成功则 ``complete_job``；可重试失败则 retry，超限或毒消息进 DLQ
5. ``finally`` 中释放租约

``WorkflowInterrupted``（审批等待）视为正常结束，任务保持 pending 供后续 resume。
``heartbeat_active_leases`` 用于长任务续租，扫描本地租约目录刷新 TTL。

潜在问题：
- ``asyncio.run`` 在同步 ``process_once`` 内调用，若外层已有事件循环会失败
- 租约获取失败时 ``_requeue`` 直接重新 enqueue，可能产生重复队列项
- cancel 命令仅 return，不更新检查点状态为 cancelled
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.worker.lease import LocalRunLeaseStore, RunLeaseStore
from safecode.enterprise.worker.models import QueueJob
from safecode.enterprise.worker.queue import CommandQueue, LocalCommandQueue, MAX_QUEUE_ATTEMPTS
from safecode.enterprise.worker.status import is_terminal
from safecode.enterprise.workflow.exceptions import WorkflowInterrupted
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator
from safecode.enterprise.workflow.types import WorkflowStatus

MAX_ATTEMPTS = MAX_QUEUE_ATTEMPTS


PersistenceBackend = object


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
        """处理单条队列任务。返回 True 表示消费了一条（含租约竞争失败的重入队）。"""
        job = self.queue.poll_pending_job()
        if job is None:
            return False
        if not self.leases.acquire(
            tenant_id=job.tenant_id,
            run_id=job.run_id,
            worker_id=self.worker_id,
            ttl_seconds=self.lease_ttl_seconds,
        ):
            # 租约被其他 worker 持有，重新入队等待下次轮询
            self._requeue(job)
            return False
        try:
            self._execute(job)
            self.queue.complete_job(job.job_id)
        except ValueError as exc:
            if str(exc).startswith("unsupported queue command"):
                self.queue.dlq_job(job.job_id, message=str(exc), poison=True)
            else:
                self._handle_failure(job, exc)
        except Exception as exc:
            self._handle_failure(job, exc)
        finally:
            self.leases.release(
                tenant_id=job.tenant_id,
                run_id=job.run_id,
                worker_id=self.worker_id,
            )
        return True

    def _handle_failure(self, job: QueueJob, exc: Exception) -> None:
        if job.attempts + 1 >= MAX_ATTEMPTS:
            self.queue.dlq_job(job.job_id, message=str(exc), poison=False)
            return
        if not self.queue.retry_job(job.job_id, message=str(exc)):
            self.queue.dlq_job(job.job_id, message=str(exc), poison=False)

    def _requeue(self, job: QueueJob) -> None:
        self.queue.enqueue_job(
            tenant_id=job.tenant_id,
            run_id=job.run_id,
            command=job.command,
            payload=job.payload,
        )

    def _execute(self, job: QueueJob) -> None:
        """根据 command 驱动编排器；终态 run 直接跳过。"""
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
                # 审批门中断：保留检查点，不视为失败
                return
            return
        if job.command == "resume":
            try:
                asyncio.run(orchestrator.resume(job.run_id, tenant_id=job.tenant_id))
            except WorkflowInterrupted:
                return
            return
        if job.command == "cancel":
            # 潜在问题：未将检查点 status 更新为 cancelled
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
