"""PostgreSQL GC artifact-delete failure compensation tests."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from safecode.enterprise.workflow.checkpoint import run_dir
from safecode.enterprise.workflow.exceptions import CheckpointCorruptedError

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


def test_gc_runs_keeps_db_row_when_artifact_delete_fails(
    postgres_backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = postgres_backend
    run_id = "run-pg-gc-fail01"
    checkpoint = sample_checkpoint(run_id=run_id, tenant_id="tenant-a")
    backend.runs.save_checkpoint(tenant_id="tenant-a", checkpoint=checkpoint)
    _backdate_checkpoint(backend, tenant_id="tenant-a", run_id=run_id)
    directory = run_dir(backend.sac_root, run_id)
    assert directory.is_dir()
    real_rmtree = shutil.rmtree

    def _fail_rmtree(path: Path, *args: object, **kwargs: object) -> None:
        if path == directory:
            raise OSError("simulated artifact delete failure")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", _fail_rmtree)

    removed = backend.runs.gc_runs(tenant_id="tenant-a", older_than_days=1)
    assert removed == []
    assert directory.is_dir()
    backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=run_id)

    monkeypatch.setattr(shutil, "rmtree", real_rmtree)
    removed_retry = backend.runs.gc_runs(tenant_id="tenant-a", older_than_days=1)
    assert run_id in removed_retry
    assert not directory.is_dir()
    with pytest.raises(CheckpointCorruptedError):
        backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=run_id)


def test_gc_skips_run_refreshed_after_candidate_selection(postgres_backend) -> None:
    backend = postgres_backend
    run_id = "run-pg-gc-race01"
    checkpoint = sample_checkpoint(run_id=run_id, tenant_id="tenant-a")
    backend.runs.save_checkpoint(tenant_id="tenant-a", checkpoint=checkpoint)
    _backdate_checkpoint(backend, tenant_id="tenant-a", run_id=run_id)
    refreshed = backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=run_id)
    backend.runs.save_checkpoint(tenant_id="tenant-a", checkpoint=refreshed)
    removed = backend.runs.gc_runs(tenant_id="tenant-a", older_than_days=1)
    assert run_id not in removed
    backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=run_id)
    assert run_dir(backend.sac_root, run_id).is_dir()


def test_gc_runs_does_not_delete_other_tenant_artifacts(postgres_backend) -> None:
    backend = postgres_backend
    for run_id, tenant in (("run-pg-gc-tena1", "tenant-a"), ("run-pg-gc-tenb1", "tenant-b")):
        checkpoint = sample_checkpoint(run_id=run_id, tenant_id=tenant)
        backend.runs.save_checkpoint(tenant_id=tenant, checkpoint=checkpoint)
        _backdate_checkpoint(backend, tenant_id=tenant, run_id=run_id)
    removed = backend.runs.gc_runs(tenant_id="tenant-a", older_than_days=1)
    assert "run-pg-gc-tena1" in removed
    assert "run-pg-gc-tenb1" not in removed
    assert run_dir(backend.sac_root, "run-pg-gc-tenb1").is_dir()
