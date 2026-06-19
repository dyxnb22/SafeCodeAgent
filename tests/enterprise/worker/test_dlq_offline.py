"""Worker DLQ and recovery tests (v2.5.2)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.worker.runner import MAX_ATTEMPTS, WorkerRunner
from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint
from safecode.enterprise.workflow.orchestrator import build_initial_state
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus


def _backend(tmp_path: Path) -> LocalBackend:
    return LocalBackend(tmp_path / ".sac")


def _seed_checkpoint(backend: LocalBackend, *, run_id: str = "run-dlq00001") -> None:
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


def test_poison_message_moves_to_dlq_without_retry(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    _seed_checkpoint(backend)
    backend.commands.enqueue_job(
        tenant_id="tenant-a", run_id="run-dlq00001", command="start"
    )
    runner = WorkerRunner(backend, worker_id="worker-a", project_root=tmp_path)
    with patch.object(
        WorkerRunner,
        "_execute",
        side_effect=ValueError("unsupported queue command: poison"),
    ):
        assert runner.process_once() is True
    dlq_path = backend.sac_root / "enterprise" / "worker" / "queue" / "dlq.jsonl"
    assert dlq_path.is_file()
    entry = json.loads(dlq_path.read_text(encoding="utf-8").splitlines()[0])
    assert entry["poison"] is True
    assert "unsupported queue command" in entry["error"]
    pending = backend.sac_root / "enterprise" / "worker" / "queue" / "pending.jsonl"
    assert not pending.is_file() or not pending.read_text(encoding="utf-8").strip()


def test_transient_failure_retries_then_dlq(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    _seed_checkpoint(backend, run_id="run-dlq00002")
    backend.commands.enqueue_job(
        tenant_id="tenant-a", run_id="run-dlq00002", command="start"
    )
    runner = WorkerRunner(backend, worker_id="worker-a", project_root=tmp_path)
    with patch.object(WorkerRunner, "_execute", side_effect=RuntimeError("transient boom")):
        for _ in range(MAX_ATTEMPTS):
            runner.process_once()
    dlq_path = backend.sac_root / "enterprise" / "worker" / "queue" / "dlq.jsonl"
    assert dlq_path.is_file()
    entry = json.loads(dlq_path.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["poison"] is False
    assert entry["attempts"] == MAX_ATTEMPTS - 1
    assert "transient boom" in entry["error"]


def test_dlq_redacts_secrets_in_error_message(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    _seed_checkpoint(backend, run_id="run-dlq00003")
    backend.commands.enqueue_job(
        tenant_id="tenant-a", run_id="run-dlq00003", command="start"
    )
    runner = WorkerRunner(backend, worker_id="worker-a", project_root=tmp_path)
    secret = "ghp_1234567890abcdefghijklmnopqrstuvwxyz12"
    with patch.object(WorkerRunner, "_execute", side_effect=RuntimeError(f"boom {secret}")):
        for _ in range(MAX_ATTEMPTS):
            runner.process_once()
    dlq_path = backend.sac_root / "enterprise" / "worker" / "queue" / "dlq.jsonl"
    entry = json.loads(dlq_path.read_text(encoding="utf-8").splitlines()[-1])
    assert secret not in entry["error"]
    assert "[REDACTED]" in entry["error"]


def test_healthy_worker_continues_after_poison(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    _seed_checkpoint(backend, run_id="run-dlq00004")
    _seed_checkpoint(backend, run_id="run-dlq00005")
    backend.commands.enqueue_job(
        tenant_id="tenant-a", run_id="run-dlq00004", command="start"
    )
    backend.commands.enqueue_job(
        tenant_id="tenant-a", run_id="run-dlq00005", command="cancel"
    )
    runner = WorkerRunner(backend, worker_id="worker-a", project_root=tmp_path)

    def _execute(self, job):  # type: ignore[no-untyped-def]
        if job.run_id == "run-dlq00004":
            raise ValueError("unsupported queue command: poison")

    with patch.object(WorkerRunner, "_execute", _execute):
        assert runner.process_once() is True
        assert runner.process_once() is True
    completed = backend.sac_root / "enterprise" / "worker" / "queue" / "completed.jsonl"
    assert completed.is_file()
    checkpoint = backend.runs.load_checkpoint(tenant_id="tenant-a", run_id="run-dlq00005")
    assert checkpoint.state.status is WorkflowStatus.pending
