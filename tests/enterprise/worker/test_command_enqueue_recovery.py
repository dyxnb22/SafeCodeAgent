"""Command record vs queue job crash-recovery and R8.1 idempotency tests."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "persistence"))
from backend_contract import sample_request  # noqa: E402

from safecode.enterprise.api.idempotency import approval_resume_idempotency_key
from safecode.enterprise.approvals.resume import ensure_approval_resume_enqueued
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.worker.commands import cancel_run, resume_run, start_run
from safecode.enterprise.worker.queue import (
    IdempotencyConflictError,
    LocalCommandQueue,
    command_job_id,
    ensure_command_enqueued,
)
from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint, save_checkpoint
from safecode.enterprise.workflow.orchestrator import build_initial_state
from safecode.enterprise.workflow.types import TaskType


def _backend(tmp_path: Path) -> LocalBackend:
    return LocalBackend(tmp_path / ".sac")


def _subject() -> RBACSubject:
    return RBACSubject(actor_id="user:dev", tenant_id="tenant-a", roles=(Role.developer,))


def _seed_checkpoint(backend: LocalBackend, *, run_id: str) -> None:
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:dev",
        repo_root=backend.sac_root.parent,
        run_id=run_id,
        tenant_id="tenant-a",
    )
    save_checkpoint(
        backend.sac_root,
        RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=run_id,
            completed_nodes=[],
            next_node="classify_request",
            state=state,
        ),
    )


def _queue_jobs(
    backend: LocalBackend,
    *,
    idempotency_key: str | None = None,
    run_id: str | None = None,
    command: str | None = None,
    payload: dict[str, str] | None = None,
    statuses: tuple[str, ...] = ("pending", "active", "completed", "failed"),
) -> list[dict[str, object]]:
    payload_dict = dict(payload or {})
    queue_root = backend.sac_root / "enterprise" / "worker" / "queue"
    filename_by_status = {
        "pending": "pending.jsonl",
        "active": "active.jsonl",
        "completed": "completed.jsonl",
        "failed": "failed.jsonl",
    }
    jobs: list[dict[str, object]] = []
    for status in statuses:
        path = queue_root / filename_by_status[status]
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if idempotency_key is not None:
                expected_id = command_job_id(tenant_id="tenant-a", idempotency_key=idempotency_key)
                if item.get("job_id") != expected_id:
                    continue
            if run_id is not None and item.get("run_id") != run_id:
                continue
            if command is not None and item.get("command") != command:
                continue
            if payload is not None and dict(item.get("payload") or {}) != payload_dict:
                continue
            jobs.append(item)
    return jobs


def _flaky_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}
    real_enqueue = LocalCommandQueue.enqueue_command_job

    def _enqueue(self: LocalCommandQueue, record: object) -> object:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated enqueue crash")
        return real_enqueue(self, record)

    monkeypatch.setattr(LocalCommandQueue, "enqueue_command_job", _enqueue)


@pytest.mark.parametrize(
    ("handler", "kwargs_factory"),
    [
        (
            "start",
            lambda backend, run_id: {
                "backend": backend,
                "queue": backend.commands,
                "tenant_id": "tenant-a",
                "idempotency_key": "recovery-start01",
                "task_type": "pr_review",
                "input_ref": "fixture.json",
                "subject": _subject(),
                "project_root": backend.sac_root.parent,
            },
        ),
        (
            "resume",
            lambda backend, run_id: {
                "backend": backend,
                "queue": backend.commands,
                "tenant_id": "tenant-a",
                "idempotency_key": "recovery-resume1",
                "run_id": run_id,
            },
        ),
        (
            "cancel",
            lambda backend, run_id: {
                "backend": backend,
                "queue": backend.commands,
                "tenant_id": "tenant-a",
                "idempotency_key": "recovery-cancel1",
                "run_id": run_id,
            },
        ),
    ],
)
def test_run_command_recovers_missing_job_after_enqueue_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    handler: str,
    kwargs_factory: object,
) -> None:
    backend = _backend(tmp_path)
    run_id = "run-recovery001"
    if handler != "start":
        _seed_checkpoint(backend, run_id=run_id)
    _flaky_enqueue(monkeypatch)
    kwargs = kwargs_factory(backend, run_id)  # type: ignore[operator]
    invoke = {
        "start": start_run,
        "resume": resume_run,
        "cancel": cancel_run,
    }[handler]
    with pytest.raises(RuntimeError, match="simulated enqueue crash"):
        invoke(**kwargs)
    record = backend.commands.get_command(
        tenant_id="tenant-a", idempotency_key=kwargs["idempotency_key"]
    )
    assert record is not None
    assert _queue_jobs(backend, idempotency_key=kwargs["idempotency_key"], statuses=("pending", "active")) == []
    accepted = invoke(**kwargs)
    assert accepted.run_id == record.run_id
    assert len(_queue_jobs(backend, idempotency_key=kwargs["idempotency_key"], statuses=("pending", "active"))) == 1
    replay = invoke(**kwargs)
    assert replay.run_id == accepted.run_id
    assert len(_queue_jobs(backend, idempotency_key=kwargs["idempotency_key"], statuses=("pending", "active"))) == 1


def test_completed_command_replay_does_not_re_enqueue(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    key = "recovery-complete1"
    run_id = "run-complete001"
    _seed_checkpoint(backend, run_id=run_id)
    ensure_command_enqueued(
        backend.commands,
        tenant_id="tenant-a",
        idempotency_key=key,
        command="resume",
        run_id=run_id,
    )
    job_id = command_job_id(tenant_id="tenant-a", idempotency_key=key)
    polled = backend.commands.poll_pending_job()
    assert polled is not None
    assert polled.job_id == job_id
    backend.commands.complete_job(job_id)
    assert _queue_jobs(backend, idempotency_key=key, statuses=("completed",)) != []
    ensure_command_enqueued(
        backend.commands,
        tenant_id="tenant-a",
        idempotency_key=key,
        command="resume",
        run_id=run_id,
    )
    assert _queue_jobs(backend, idempotency_key=key, statuses=("pending", "active")) == []
    assert len(_queue_jobs(backend, idempotency_key=key, statuses=("completed",))) == 1


def test_concurrent_recovery_enqueues_single_job(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    run_id = "run-concurrent1"
    _seed_checkpoint(backend, run_id=run_id)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            barrier.wait()
            ensure_command_enqueued(
                backend.commands,
                tenant_id="tenant-a",
                idempotency_key="recovery-concur1",
                command="resume",
                run_id=run_id,
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert (
        len(
            _queue_jobs(
                backend,
                idempotency_key="recovery-concur1",
                statuses=("pending", "active", "completed", "failed"),
            )
        )
        == 1
    )


def test_reused_key_with_different_run_raises(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    _seed_checkpoint(backend, run_id="run-conflict01")
    _seed_checkpoint(backend, run_id="run-conflict02")
    ensure_command_enqueued(
        backend.commands,
        tenant_id="tenant-a",
        idempotency_key="recovery-conflict",
        command="resume",
        run_id="run-conflict01",
    )
    with pytest.raises(IdempotencyConflictError):
        resume_run(
            backend,
            backend.commands,
            tenant_id="tenant-a",
            idempotency_key="recovery-conflict",
            run_id="run-conflict02",
        )


def test_start_run_replay_validates_payload(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    start_run(
        backend,
        backend.commands,
        tenant_id="tenant-a",
        idempotency_key="recovery-payload1",
        task_type="pr_review",
        input_ref=str(fixture),
        subject=_subject(),
        project_root=tmp_path,
    )
    with pytest.raises(IdempotencyConflictError):
        start_run(
            backend,
            backend.commands,
            tenant_id="tenant-a",
            idempotency_key="recovery-payload1",
            task_type="pr_review",
            input_ref=str(tmp_path / "other.json"),
            subject=_subject(),
            project_root=tmp_path,
        )


@pytest.mark.parametrize("decision", ["approved", "rejected", "revoked"])
def test_approval_resume_recovers_after_enqueue_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
) -> None:
    backend = _backend(tmp_path)
    run_id = "run-approval001"
    _seed_checkpoint(backend, run_id=run_id)
    request = sample_request(run_id=run_id, request_id=f"approval-{decision[:3]}01")
    resume_key = approval_resume_idempotency_key(
        tenant_id="tenant-a",
        approval_id=request.request_id,
        decision=decision,
    )
    _flaky_enqueue(monkeypatch)
    with pytest.raises(RuntimeError, match="simulated enqueue crash"):
        ensure_approval_resume_enqueued(
            backend,
            tenant_id="tenant-a",
            request=request,
            decision=decision,
        )
    ensure_approval_resume_enqueued(
        backend,
        tenant_id="tenant-a",
        request=request,
        decision=decision,
    )
    assert len(_queue_jobs(backend, idempotency_key=resume_key, statuses=("pending", "active"))) == 1
    ensure_approval_resume_enqueued(
        backend,
        tenant_id="tenant-a",
        request=request,
        decision=decision,
    )
    assert len(_queue_jobs(backend, idempotency_key=resume_key, statuses=("pending", "active"))) <= 1
