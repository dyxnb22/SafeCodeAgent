"""Tests for v4.3 fix-loop iteration records."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from safecode.cli_fix import run_fix
from safecode.task.store import TaskStore
from safecode.task.wiring import record_fix_on_task


def _edit_result(tmp_path: Path) -> MagicMock:
    result = MagicMock()
    result.pending_patch_path = tmp_path / ".sac" / "pending_patch.json"
    result.diff_text = "--- a/foo.py\n+++ b/foo.py\n"
    result.proposal.id = "patch-123"
    return result


def test_plain_fix_records_one_proposed_iteration(tmp_path: Path) -> None:
    with (
        patch("safecode.cli_fix._run_test_command") as mock_run,
        patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
    ):
        mock_run.return_value = ("FAILED test_token=secret-value", 1)
        MockOrch.return_value.edit.return_value = _edit_result(tmp_path)
        code = run_fix(tmp_path, test_command="pytest -q")

    assert code == 0
    state = TaskStore(tmp_path).load(TaskStore(tmp_path).current_id() or "")
    assert state is not None
    assert len([i for i in state.iterations if i.event == "fix"]) == 1
    iteration = state.iterations[-1]
    assert iteration.iteration_index == 0
    assert iteration.mode == "plain"
    assert iteration.test_command == "pytest -q"
    assert iteration.test_exit_code == 1
    assert iteration.exit_code == 1
    assert iteration.pending_patch_id == "patch-123"
    assert iteration.pending_patch_path.endswith("pending_patch.json")
    assert iteration.status == "proposed"
    assert iteration.tail_hash == iteration.failure_tail_sha256


def test_iteration_hash_uses_bounded_redacted_tail(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    state = store.create("hash test")
    secret = "token=raw-secret-value"
    redacted_tail = "prefix\n" + ("x" * 12_500) + "\n[REDACTED]"

    record_fix_on_task(
        tmp_path,
        state.task_id,
        "pytest -q",
        1,
        redacted_tail,
        mode="watch",
        status="proposed",
    )

    loaded = store.load(state.task_id)
    assert loaded is not None
    dumped = loaded.model_dump_json()
    assert secret not in dumped
    iteration = loaded.iterations[-1]
    assert iteration.tail_hash is not None
    assert len(iteration.tail_hash) == 64


def test_iterations_are_append_only(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    state = store.create("append")

    record_fix_on_task(tmp_path, state.task_id, "pytest -q", 1, "one", status="proposed")
    record_fix_on_task(tmp_path, state.task_id, "pytest -q", 1, "two", status="proposed")

    loaded = store.load(state.task_id)
    assert loaded is not None
    assert [i.iteration_index for i in loaded.iterations] == [0, 1]
    assert [i.status for i in loaded.iterations] == ["proposed", "proposed"]
