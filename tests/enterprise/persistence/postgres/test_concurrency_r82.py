"""R8.2 PostgreSQL command claim and checkpoint/GC concurrency tests."""

from __future__ import annotations

import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.persistence.run_artifact_lock import (
    run_artifact_lock,
    run_artifact_lock_path,
)
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.worker.commands import start_run
from safecode.enterprise.workflow.checkpoint import run_dir
from safecode.enterprise.workflow.ids import generate_run_id
from safecode.enterprise.workflow.orchestrator import utc_now_iso

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend_contract import sample_checkpoint  # noqa: E402


def _backdate_checkpoint(backend, *, tenant_id: str, run_id: str) -> None:
    with backend.pool.connection() as conn:
        conn.execute(
            """
            UPDATE enterprise.checkpoints
            SET updated_at = NOW() - INTERVAL '30 days'
            WHERE tenant_id = %s AND run_id = %s
            """,
            (tenant_id, run_id),
        )
        conn.commit()


def _subject() -> RBACSubject:
    return RBACSubject(actor_id="user:dev", tenant_id="tenant-a", roles=(Role.developer,))


def test_concurrent_postgres_record_command_returns_single_winner(postgres_backend) -> None:
    queue = postgres_backend.commands
    barrier = threading.Barrier(2)
    records: list[object] = []
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            barrier.wait()
            records.append(
                queue.record_command(
                    tenant_id="tenant-a",
                    idempotency_key="pg-record-concur1",
                    command="start",
                    run_id=generate_run_id(),
                    payload={"task_type": "pr_review", "input_ref": "fixture.json"},
                )
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(records) == 2
    assert records[0].run_id == records[1].run_id  # type: ignore[attr-defined]


def test_concurrent_postgres_start_run_single_checkpoint(
    postgres_backend, tmp_path: Path
) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    barrier = threading.Barrier(2)
    accepted: list[object] = []
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            barrier.wait()
            accepted.append(
                start_run(
                    postgres_backend,
                    postgres_backend.commands,
                    tenant_id="tenant-a",
                    idempotency_key="pg-start-concur1",
                    task_type="pr_review",
                    input_ref=str(fixture),
                    subject=_subject(),
                    project_root=tmp_path,
                )
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    run_ids = {item.run_id for item in accepted}  # type: ignore[attr-defined]
    assert len(run_ids) == 1
    run_id = next(iter(run_ids))
    postgres_backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=run_id)
    assert run_dir(postgres_backend.sac_root, run_id).is_dir()
    with postgres_backend.pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT run_id FROM enterprise.checkpoints
            WHERE tenant_id = %s AND run_id = %s
            """,
            ("tenant-a", run_id),
        ).fetchall()
    assert len(rows) == 1


def test_gc_and_save_checkpoint_remain_consistent_under_contention(
    postgres_backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = postgres_backend
    run_id = "run-pg-gc-save01"
    checkpoint = sample_checkpoint(run_id=run_id, tenant_id="tenant-a")
    backend.runs.save_checkpoint(tenant_id="tenant-a", checkpoint=checkpoint)
    _backdate_checkpoint(backend, tenant_id="tenant-a", run_id=run_id)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []
    real_rmtree = shutil.rmtree

    def _slow_rmtree(path: Path, *args: object, **kwargs: object) -> None:
        if path == run_dir(backend.sac_root, run_id):
            time.sleep(0.15)
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", _slow_rmtree)

    def _gc_worker() -> None:
        try:
            barrier.wait()
            backend.runs.gc_runs(tenant_id="tenant-a", older_than_days=1)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    def _save_worker() -> None:
        try:
            barrier.wait()
            refreshed = backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=run_id)
            updated_state = refreshed.state.model_copy(update={"updated_at": utc_now_iso()})
            backend.runs.save_checkpoint(
                tenant_id="tenant-a",
                checkpoint=refreshed.model_copy(update={"state": updated_state}),
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [
        threading.Thread(target=_gc_worker),
        threading.Thread(target=_save_worker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    loaded = backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=run_id)
    assert loaded.run_id == run_id
    assert (run_dir(backend.sac_root, run_id) / "state.json").is_file()


def test_concurrent_local_start_run_single_checkpoint(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    barrier = threading.Barrier(2)
    accepted: list[object] = []
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            barrier.wait()
            accepted.append(
                start_run(
                    backend,
                    backend.commands,
                    tenant_id="tenant-a",
                    idempotency_key="local-start-con1",
                    task_type="pr_review",
                    input_ref=str(fixture),
                    subject=_subject(),
                    project_root=tmp_path,
                )
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    run_ids = {item.run_id for item in accepted}  # type: ignore[attr-defined]
    assert len(run_ids) == 1
    run_id = next(iter(run_ids))
    backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=run_id)
    assert run_dir(backend.sac_root, run_id).is_dir()


def test_start_replay_recovers_claim_without_checkpoint(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    claimed_run_id = "run-claimed001"
    backend.commands.record_command(
        tenant_id="tenant-a",
        idempotency_key="local-start-claim1",
        command="start",
        run_id=claimed_run_id,
        payload={
            "task_type": "pr_review",
            "input_ref": str(fixture),
            "actor_id": "user:dev",
        },
    )

    accepted = start_run(
        backend,
        backend.commands,
        tenant_id="tenant-a",
        idempotency_key="local-start-claim1",
        task_type="pr_review",
        input_ref=str(fixture),
        subject=_subject(),
        project_root=tmp_path,
    )

    assert accepted.run_id == claimed_run_id
    checkpoint = backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=claimed_run_id)
    assert checkpoint.state.actor_id == "user:dev"


def test_run_artifact_lock_survives_run_directory_removal(tmp_path: Path) -> None:
    artifacts_root = tmp_path / ".sac"
    run_id = "run-lockstable1"
    lock_path = run_artifact_lock_path(
        artifacts_root,
        tenant_id="tenant-a",
        run_id=run_id,
    )
    directory = run_dir(artifacts_root, run_id)
    with run_artifact_lock(artifacts_root, tenant_id="tenant-a", run_id=run_id):
        directory.mkdir(parents=True)
        (directory / "state.json").write_text("{}", encoding="utf-8")
        shutil.rmtree(directory)
        assert lock_path.is_file()
        assert directory not in lock_path.parents
    assert lock_path.is_file()
