"""R8 tenant-safe purge and GC regression tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from safecode.enterprise.persistence.exceptions import TenantBoundaryError
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.persistence.strict_fake import StrictFakeBackend
from safecode.enterprise.workflow.checkpoint import (
    CHECKPOINT_SCHEMA_VERSION,
    RunCheckpoint,
    gc_runs,
    run_dir,
    save_checkpoint,
)
from safecode.enterprise.workflow.exceptions import CheckpointCorruptedError
from safecode.enterprise.workflow.orchestrator import build_initial_state
from safecode.enterprise.workflow.types import TaskType

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backend_contract import sample_checkpoint  # noqa: E402


def _state(tmp_path: Path, *, run_id: str, tenant_id: str):
    return build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
        tenant_id=tenant_id,
    )


def test_tenant_b_cannot_purge_tenant_a_run(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    checkpoint = sample_checkpoint(run_id="run-purge0001", tenant_id="tenant-a")
    backend.runs.save_checkpoint(tenant_id="tenant-a", checkpoint=checkpoint)
    with pytest.raises(TenantBoundaryError):
        backend.runs.purge_run(tenant_id="tenant-b", run_id="run-purge0001")
    assert run_dir(backend.sac_root, "run-purge0001").is_dir()


def test_orphan_run_without_state_not_purged(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    directory = run_dir(backend.sac_root, "run-orphan001")
    directory.mkdir(parents=True)
    with pytest.raises(CheckpointCorruptedError):
        backend.runs.purge_run(tenant_id="tenant-a", run_id="run-orphan001")
    assert directory.is_dir()


def test_corrupt_state_not_purged(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    directory = run_dir(backend.sac_root, "run-corrupt01")
    directory.mkdir(parents=True)
    (directory / "state.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(CheckpointCorruptedError):
        backend.runs.purge_run(tenant_id="tenant-a", run_id="run-corrupt01")
    assert directory.is_dir()


def test_gc_only_removes_matching_tenant_runs(tmp_path: Path) -> None:
    import os
    import time

    sac_root = tmp_path / ".sac"
    old = time.time() - 200000
    for run_id, tenant in (("run-gc-tenanta", "tenant-a"), ("run-gc-tenantb", "tenant-b")):
        state = _state(tmp_path, run_id=run_id, tenant_id=tenant)
        save_checkpoint(
            sac_root,
            RunCheckpoint(
                schema_version=CHECKPOINT_SCHEMA_VERSION,
                run_id=run_id,
                completed_nodes=[],
                next_node="classify_request",
                state=state,
            ),
        )
        run_path = run_dir(sac_root, run_id)
        os.utime(run_path, (old, old))
        os.utime(run_path / "state.json", (old, old))
    removed = gc_runs(sac_root, tenant_id="tenant-a", older_than_days=1)
    assert "run-gc-tenanta" in removed
    assert "run-gc-tenantb" not in removed
    assert run_dir(sac_root, "run-gc-tenantb").is_dir()


def test_gc_skips_symlink_run_directory(tmp_path: Path) -> None:
    sac_root = tmp_path / ".sac"
    runs = sac_root / "enterprise" / "runs"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    runs.mkdir(parents=True)
    link = runs / "run-link00002"
    link.symlink_to(outside, target_is_directory=True)
    removed = gc_runs(sac_root, tenant_id="tenant-a", older_than_days=1)
    assert "run-link00002" not in removed
    assert (outside / "secret.txt").exists()


def test_strict_fake_purge_requires_checkpoint(tmp_path: Path) -> None:
    backend = StrictFakeBackend(tmp_path / ".sac")
    with pytest.raises(CheckpointCorruptedError):
        backend.runs.purge_run(tenant_id="tenant-a", run_id="run-missing01")
