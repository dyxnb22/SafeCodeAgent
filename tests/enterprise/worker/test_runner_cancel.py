"""Worker cancel command persistence tests."""

from __future__ import annotations

from pathlib import Path

from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.worker.runner import WorkerRunner
from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint
from safecode.enterprise.workflow.orchestrator import build_initial_state
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus


def _backend(tmp_path: Path) -> LocalBackend:
    return LocalBackend(tmp_path / ".sac")


def _seed_checkpoint(backend: LocalBackend, *, run_id: str = "run-cancel0001") -> None:
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


def test_worker_cancel_persists_cancelled_checkpoint(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    run_id = "run-cancel0001"
    _seed_checkpoint(backend, run_id=run_id)
    backend.commands.enqueue_job(tenant_id="tenant-a", run_id=run_id, command="cancel")

    runner = WorkerRunner(backend, worker_id="worker-a", project_root=tmp_path)
    assert runner.process_once() is True

    checkpoint = backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=run_id)
    assert checkpoint.state.status is WorkflowStatus.cancelled
