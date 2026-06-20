"""R8 worker lease heartbeat and fencing regression tests."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.worker.heartbeat import LeaseHeartbeatGuard
from safecode.enterprise.worker.runner import WorkerRunner
from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint
from safecode.enterprise.workflow.orchestrator import build_initial_state
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus


def _backend(tmp_path: Path) -> LocalBackend:
    return LocalBackend(tmp_path / ".sac")


def _seed_run(backend: LocalBackend, *, run_id: str = "run-heartbeat1") -> None:
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=backend.sac_root.parent,
        run_id=run_id,
        tenant_id="tenant-a",
    )
    backend.runs.save_checkpoint(
        tenant_id="tenant-a",
        checkpoint=RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=run_id,
            completed_nodes=[],
            next_node="classify_request",
            state=state,
        ),
    )


def test_heartbeat_extends_expiry_during_guard(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    leases = backend.leases
    leases.acquire(
        tenant_id="tenant-a",
        run_id="run-heartbeat1",
        worker_id="worker-a",
        ttl_seconds=2,
    )
    fence = leases.read_fence_token(
        tenant_id="tenant-a", run_id="run-heartbeat1", worker_id="worker-a"
    )
    assert fence is not None
    guard = LeaseHeartbeatGuard(
        leases=leases,
        tenant_id="tenant-a",
        run_id="run-heartbeat1",
        worker_id="worker-a",
        fence_token=fence,
        ttl_seconds=2,
    )
    guard.start()
    try:
        time.sleep(1.2)
        assert leases.holds_lease(
            tenant_id="tenant-a",
            run_id="run-heartbeat1",
            worker_id="worker-a",
            fence_token=fence,
        )
        assert not leases.acquire(
            tenant_id="tenant-a",
            run_id="run-heartbeat1",
            worker_id="worker-b",
            ttl_seconds=2,
        )
    finally:
        guard.stop()
        assert guard._thread is None or not guard._thread.is_alive()


def test_second_worker_blocked_while_heartbeat_guard_active(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    leases = backend.leases
    leases.acquire(
        tenant_id="tenant-a",
        run_id="run-heartbeat2",
        worker_id="worker-a",
        ttl_seconds=2,
    )
    fence = leases.read_fence_token(
        tenant_id="tenant-a", run_id="run-heartbeat2", worker_id="worker-a"
    )
    assert fence is not None
    guard = LeaseHeartbeatGuard(
        leases=leases,
        tenant_id="tenant-a",
        run_id="run-heartbeat2",
        worker_id="worker-a",
        fence_token=fence,
        ttl_seconds=2,
    )
    guard.start()
    try:
        time.sleep(1.5)
        assert not leases.acquire(
            tenant_id="tenant-a",
            run_id="run-heartbeat2",
            worker_id="worker-b",
            ttl_seconds=2,
        )
    finally:
        guard.stop()


def test_runner_does_not_complete_after_lease_takeover(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    run_id = "run-stale0001"
    _seed_run(backend, run_id=run_id)
    backend.commands.enqueue_job(tenant_id="tenant-a", run_id=run_id, command="cancel")
    runner_a = WorkerRunner(
        backend, worker_id="worker-a", project_root=tmp_path, lease_ttl_seconds=5
    )
    runner_b = WorkerRunner(
        backend, worker_id="worker-b", project_root=tmp_path, lease_ttl_seconds=5
    )

    started = threading.Event()
    release = threading.Event()
    lease_path = (
        backend.sac_root / "enterprise" / "worker" / "leases" / "tenant-a" / f"{run_id}.json"
    )

    def slow_execute(job):  # type: ignore[no-untyped-def]
        started.set()
        payload = json.loads(lease_path.read_text(encoding="utf-8"))
        payload["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=30)
        ).isoformat()
        lease_path.write_text(json.dumps(payload), encoding="utf-8")
        assert runner_b.leases.acquire(
            tenant_id="tenant-a", run_id=run_id, worker_id="worker-b", ttl_seconds=30
        )
        release.wait(timeout=3)

    with patch.object(LeaseHeartbeatGuard, "start", lambda self: None):
        with patch.object(WorkerRunner, "_execute", side_effect=slow_execute):
            thread = threading.Thread(target=runner_a.process_once)
            thread.start()
            assert started.wait(timeout=2)
            release.set()
            thread.join(timeout=3)
    completed = backend.sac_root / "enterprise" / "worker" / "queue" / "completed.jsonl"
    assert not completed.is_file() or "run-stale0001" not in completed.read_text(encoding="utf-8")
    fence_b = runner_b.leases.read_fence_token(
        tenant_id="tenant-a", run_id=run_id, worker_id="worker-b"
    )
    assert fence_b is not None
    assert runner_b.leases.holds_lease(
        tenant_id="tenant-a",
        run_id=run_id,
        worker_id="worker-b",
        fence_token=fence_b,
    )


def test_heartbeat_guard_stops_cleanly_on_exception(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    failing = MagicMock()
    failing.heartbeat.side_effect = RuntimeError("heartbeat failed")
    guard = LeaseHeartbeatGuard(
        leases=failing,
        tenant_id="tenant-a",
        run_id="run-heartbeat3",
        worker_id="worker-a",
        fence_token="fence-token",
        ttl_seconds=3,
    )
    guard.start()
    deadline = time.time() + 3
    while time.time() < deadline and not guard.ownership_lost():
        time.sleep(0.05)
    guard.stop()
    assert guard.ownership_lost()
    assert guard._thread is None or not guard._thread.is_alive()
