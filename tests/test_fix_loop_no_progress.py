"""Tests for v4.3.1 fix-loop no-progress detection."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from safecode.cli_fix import run_fix_watch
from safecode.task.store import TaskStore
from safecode.task.wiring import record_fix_on_task


def test_repeated_tail_hash_stops_without_new_proposal(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    state = store.create("no progress")
    failure = "same failing tail"
    record_fix_on_task(tmp_path, state.task_id, "pytest -q", 1, failure, mode="watch", status="proposed")

    with (
        patch("safecode.cli_fix._run_test_command") as mock_run,
        patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
    ):
        mock_run.return_value = (failure, 1)
        code = run_fix_watch(tmp_path, test_command="pytest -q")

    assert code == 1
    MockOrch.return_value.edit.assert_not_called()
    loaded = store.load(state.task_id)
    assert loaded is not None
    assert loaded.iterations[-1].failure_category == "loop_no_progress"
    assert loaded.iterations[-1].status == "failed"


def test_no_progress_json_shape(tmp_path: Path, capsys) -> None:
    store = TaskStore(tmp_path)
    state = store.create("json")
    failure = "same failing tail"
    record_fix_on_task(tmp_path, state.task_id, "pytest -q", 1, failure, mode="watch", status="proposed")

    with patch("safecode.cli_fix._run_test_command") as mock_run:
        mock_run.return_value = (failure, 1)
        run_fix_watch(tmp_path, test_command="pytest -q", json_output=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["data"]["failure_category"] == "loop_no_progress"
    assert payload["data"]["test_exit_code"] == 1
    assert "sac status" in payload["data"]["next_step"]
    assert "No progress" in payload["error"]
