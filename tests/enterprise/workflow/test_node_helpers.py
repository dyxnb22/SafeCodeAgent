"""Workflow node helper tests."""

from __future__ import annotations

from pathlib import Path

from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.orchestrator import build_initial_state
from safecode.enterprise.workflow.types import TaskType


def test_build_patch_propagates_soft_failure_status(tmp_path: Path) -> None:
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-helper0001",
    )
    patch = build_patch(
        state,
        "validate_outputs",
        summary="validation failed",
        status="soft_failure",
    )
    output = patch.state_updates["node_outputs"]["validate_outputs"]
    assert output.status == "soft_failure"
    assert patch.status == "soft_failure"
