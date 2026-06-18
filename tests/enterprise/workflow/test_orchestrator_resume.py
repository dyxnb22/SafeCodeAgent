"""Orchestrator resume and checkpoint security tests (v1.2.2-T2)."""

import asyncio
import json
import os
from pathlib import Path

import pytest

from safecode.enterprise.workflow.checkpoint import gc_runs, load_checkpoint, run_dir, save_checkpoint
from safecode.enterprise.workflow.exceptions import (
    CheckpointCorruptedError,
    InvalidRunIdError,
    InvalidStateSchemaVersionError,
    WorkflowInterrupted,
)
from safecode.enterprise.workflow.ids import validate_run_id
from safecode.enterprise.workflow.nodes.registry import WORKFLOW_NODE_ORDER
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus


def test_resume_skips_completed_nodes(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-resume0001",
    )
    from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint

    partial = list(WORKFLOW_NODE_ORDER[:3])
    save_checkpoint(
        sac_root,
        RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=state.run_id,
            completed_nodes=partial,
            next_node=WORKFLOW_NODE_ORDER[3],
            state=state.model_copy(update={"status": WorkflowStatus.running}),
        ),
    )
    completed_before = len(partial)
    final = asyncio.run(orchestrator.resume("run-resume0001"))
    assert final.status == WorkflowStatus.succeeded
    assert len(load_checkpoint(sac_root, "run-resume0001").completed_nodes) >= completed_before


def test_malformed_checkpoint_fail_closed(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    directory = run_dir(sac_root, "run-bad000001")
    directory.mkdir(parents=True)
    (directory / "state.json").write_text("{not-json", encoding="utf-8")
    with pytest.raises(CheckpointCorruptedError):
        load_checkpoint(sac_root, "run-bad000001")


def test_incompatible_checkpoint_schema(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    directory = run_dir(sac_root, "run-bad000002")
    directory.mkdir(parents=True)
    (directory / "state.json").write_text(
        json.dumps({"schema_version": "9.9.9", "completed_nodes": [], "state": {}}),
        encoding="utf-8",
    )
    with pytest.raises((InvalidStateSchemaVersionError, CheckpointCorruptedError)):
        load_checkpoint(sac_root, "run-bad000002")


def test_run_id_path_traversal_rejected():
    with pytest.raises(InvalidRunIdError):
        validate_run_id("run-../escape")


def test_symlink_escape_not_followed_for_gc(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    runs = sac_root / "enterprise" / "runs"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    runs.mkdir(parents=True)
    link = runs / "run-link00001"
    link.symlink_to(outside, target_is_directory=True)
    removed = gc_runs(sac_root, older_than_days=1)
    assert "run-link00001" not in removed
    assert (outside / "secret.txt").exists()


def test_atomic_write_leaves_valid_json(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-atomic001",
    )
    from safecode.enterprise.workflow.checkpoint import RunCheckpoint

    save_checkpoint(
        sac_root,
        RunCheckpoint(
            schema_version="1.2.0",
            run_id=state.run_id,
            completed_nodes=[WORKFLOW_NODE_ORDER[0]],
            next_node=WORKFLOW_NODE_ORDER[1],
            state=state,
        ),
    )
    payload = json.loads((run_dir(sac_root, state.run_id) / "state.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == state.run_id
    assert not list(run_dir(sac_root, state.run_id).glob("*.tmp"))
