"""Local worker queue and lease concurrency regression tests."""

from __future__ import annotations

import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from safecode.enterprise.worker.lease import LocalRunLeaseStore
from safecode.enterprise.worker.queue import LocalCommandQueue


def test_queue_poll_claims_each_job_once(tmp_path: Path) -> None:
    workers = 10

    def poll_once(queue: LocalCommandQueue, barrier: threading.Barrier, claimed: list[str]) -> None:
        barrier.wait()
        job = queue.poll_pending_job()
        if job is not None:
            claimed.append(job.job_id)

    for iteration in range(10):
        sac_root = tmp_path / f"queue-{iteration}" / ".sac"
        queue = LocalCommandQueue(sac_root)
        for index in range(5):
            queue.enqueue_job(
                tenant_id="local",
                run_id=f"run-{index}",
                command="start",
            )
        claimed: list[str] = []
        barrier = threading.Barrier(workers)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(poll_once, queue, barrier, claimed) for _ in range(workers)
            ]
            for future in as_completed(futures):
                future.result()
        assert len(claimed) == 5
        assert len(set(claimed)) == 5


def test_lease_acquire_grants_single_owner(tmp_path: Path) -> None:
    for iteration in range(10):
        sac_root = tmp_path / f"lease-{iteration}" / ".sac"
        leases = LocalRunLeaseStore(sac_root)
        winners: list[str] = []
        barrier = threading.Barrier(16)

        def acquire_once(worker_id: str) -> None:
            barrier.wait()
            if leases.acquire(
                tenant_id="local", run_id="run-lease001", worker_id=worker_id, ttl_seconds=30
            ):
                winners.append(worker_id)

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [
                pool.submit(acquire_once, f"worker-{index}") for index in range(16)
            ]
            for future in as_completed(futures):
                future.result()
        assert len(winners) == 1


def _mp_poll_worker(sac_root: str, ready, claimed) -> None:
    ready.wait()
    job = LocalCommandQueue(Path(sac_root)).poll_pending_job()
    if job is not None:
        claimed.append(job.job_id)


def test_queue_poll_multiprocess_single_claim_per_job(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    for iteration in range(10):
        sac_root = tmp_path / f"queue-mp-{iteration}" / ".sac"
        queue = LocalCommandQueue(sac_root)
        for index in range(4):
            queue.enqueue_job(
                tenant_id="local",
                run_id=f"run-mp-{index}",
                command="start",
            )
        manager = ctx.Manager()
        ready = ctx.Barrier(8)
        claimed = manager.list()
        processes = [
            ctx.Process(target=_mp_poll_worker, args=(str(sac_root), ready, claimed))
            for _ in range(8)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0
        assert len(claimed) == 4
        assert len(set(claimed)) == 4


def _mp_lease_worker(sac_root: str, worker_id: str, ready, winners) -> None:
    ready.wait()
    leases = LocalRunLeaseStore(Path(sac_root))
    if leases.acquire(
        tenant_id="local",
        run_id="run-lease-mp01",
        worker_id=worker_id,
        ttl_seconds=30,
    ):
        winners.append(worker_id)


def test_lease_acquire_multiprocess_single_owner(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    for iteration in range(10):
        sac_root = tmp_path / f"lease-mp-{iteration}" / ".sac"
        manager = ctx.Manager()
        ready = ctx.Barrier(8)
        winners = manager.list()
        processes = [
            ctx.Process(
                target=_mp_lease_worker,
                args=(str(sac_root), f"worker-{index}", ready, winners),
            )
            for index in range(8)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0
        assert len(winners) == 1
