"""Worker lease and recovery tests (v2.1.5-T3)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.worker.lease import LocalRunLeaseStore
from safecode.enterprise.worker.runner import WorkerRunner


def _backend(tmp_path: Path) -> LocalBackend:
    return LocalBackend(tmp_path / ".sac")


def test_lease_acquire_release_is_atomic(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    leases = LocalRunLeaseStore(backend.sac_root)
    assert leases.acquire(
        tenant_id="tenant-a", run_id="run-lease0001", worker_id="worker-a", ttl_seconds=30
    )
    assert not leases.acquire(
        tenant_id="tenant-a", run_id="run-lease0001", worker_id="worker-b", ttl_seconds=30
    )
    leases.release(tenant_id="tenant-a", run_id="run-lease0001", worker_id="worker-a")
    assert leases.acquire(
        tenant_id="tenant-a", run_id="run-lease0001", worker_id="worker-b", ttl_seconds=30
    )


def test_heartbeat_refreshes_expiry(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    leases = LocalRunLeaseStore(backend.sac_root)
    leases.acquire(
        tenant_id="tenant-a", run_id="run-lease0002", worker_id="worker-a", ttl_seconds=5
    )
    assert leases.heartbeat(
        tenant_id="tenant-a", run_id="run-lease0002", worker_id="worker-a", ttl_seconds=60
    )
    path = backend.sac_root / "enterprise" / "worker" / "leases" / "tenant-a" / "run-lease0002.json"
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))
    expires = datetime.fromisoformat(payload["expires_at"])
    assert expires > datetime.now(timezone.utc) + timedelta(seconds=30)


def test_expired_lease_allows_takeover(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    leases = LocalRunLeaseStore(backend.sac_root)
    path = backend.sac_root / "enterprise" / "worker" / "leases" / "tenant-a" / "run-lease0003.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    expired = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    path.write_text(
        __import__("json").dumps(
            {
                "tenant_id": "tenant-a",
                "run_id": "run-lease0003",
                "worker_id": "worker-a",
                "expires_at": expired,
                "heartbeat_at": expired,
            }
        ),
        encoding="utf-8",
    )
    assert leases.acquire(
        tenant_id="tenant-a", run_id="run-lease0003", worker_id="worker-b", ttl_seconds=30
    )


def test_worker_skips_when_lease_unavailable(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    backend.commands.enqueue_job(
        tenant_id="tenant-a", run_id="run-worker001", command="cancel"
    )
    backend.leases.acquire(
        tenant_id="tenant-a", run_id="run-worker001", worker_id="worker-a", ttl_seconds=60
    )
    runner = WorkerRunner(backend, worker_id="worker-b", project_root=tmp_path)
    assert runner.process_once() is False
    pending = backend.sac_root / "enterprise" / "worker" / "queue" / "pending.jsonl"
    assert pending.is_file()
    assert pending.read_text(encoding="utf-8").strip()


def test_worker_recovery_requeues_after_retryable_failure(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    state = __import__(
        "safecode.enterprise.workflow.orchestrator", fromlist=["build_initial_state"]
    ).build_initial_state(
        task_type=__import__(
            "safecode.enterprise.workflow.types", fromlist=["TaskType"]
        ).TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-worker002",
        tenant_id="tenant-a",
    )
    from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint

    backend.runs.save_checkpoint(
        tenant_id="tenant-a",
        checkpoint=RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id="run-worker002",
            completed_nodes=[],
            next_node="classify_request",
            state=state,
        ),
    )
    backend.commands.enqueue_job(
        tenant_id="tenant-a", run_id="run-worker002", command="start"
    )
    runner = WorkerRunner(backend, worker_id="worker-a", project_root=tmp_path)
    with patch.object(WorkerRunner, "_execute", side_effect=RuntimeError("retry me")):
        assert runner.process_once() is True
    pending = backend.sac_root / "enterprise" / "worker" / "queue" / "pending.jsonl"
    assert pending.is_file()
    line = json.loads(pending.read_text(encoding="utf-8").splitlines()[0])
    assert line["attempts"] == 1
    assert "retry me" in line["payload"]["last_error"]
