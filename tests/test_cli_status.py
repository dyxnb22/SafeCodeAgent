"""Tests for sac status command (v4.1.1 T-4.1.1-A)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.cli_status import next_step
from safecode.task.state import TaskCommand, TaskIteration, TaskState
from safecode.task.store import TaskStore

runner = CliRunner()


# ---------------------------------------------------------------------------
# next_step pure function tests (truth table)
# ---------------------------------------------------------------------------

class TestNextStep:
    def test_no_state(self):
        result = next_step(None, pending_patch_exists=False)
        assert "sac task new" in result

    def test_no_state_patch_exists(self):
        result = next_step(None, pending_patch_exists=True)
        assert "sac task new" in result

    def test_open_with_pending_patch(self):
        state = TaskState(task_id="t-abc12345", goal="fix test")
        result = next_step(state, pending_patch_exists=True)
        assert "sac apply" in result

    def test_open_no_patch_last_test_failed(self):
        iter_ = TaskIteration(iteration_index=0, event="fix", test_command="pytest", test_exit_code=1)
        state = TaskState(task_id="t-abc12345", goal="fix test", iterations=[iter_])
        result = next_step(state, pending_patch_exists=False)
        assert "sac fix" in result

    def test_open_no_patch_last_test_passed(self):
        iter_ = TaskIteration(iteration_index=0, event="fix", test_command="pytest", test_exit_code=0)
        state = TaskState(task_id="t-abc12345", goal="fix test", iterations=[iter_])
        result = next_step(state, pending_patch_exists=False)
        # No failing test, no pending patch: suggest edit
        assert "sac edit" in result

    def test_open_no_iterations_no_patch(self):
        state = TaskState(task_id="t-abc12345", goal="add feature")
        result = next_step(state, pending_patch_exists=False)
        assert "sac edit" in result

    def test_applied_status(self):
        state = TaskState(task_id="t-abc12345", goal="done", status="applied")
        result = next_step(state, pending_patch_exists=False)
        assert "applied" in result.lower()

    def test_interrupted_status(self):
        state = TaskState(task_id="t-abc12345", goal="interrupted", status="interrupted")
        result = next_step(state, pending_patch_exists=False)
        assert "interrupted" in result.lower() or "resume" in result.lower()

    def test_closed_status(self):
        state = TaskState(task_id="t-abc12345", goal="closed", status="closed")
        result = next_step(state, pending_patch_exists=False)
        assert "sac task new" in result


# ---------------------------------------------------------------------------
# sac status CLI tests
# ---------------------------------------------------------------------------

class TestStatusCommand:
    def test_status_no_task(self, tmp_path):
        with patch("safecode.cli_status.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0

    def test_status_json_no_task(self, tmp_path):
        with patch("safecode.cli_status.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["command"] == "status"
        assert data["status"] == "success"
        assert "task_id" in data["data"]
        assert data["data"]["task_id"] is None
        assert "next_step" in data["data"]

    def test_status_json_with_task(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("add /health route")
        with patch("safecode.cli_status.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["task_id"] == state.task_id
        assert data["data"]["status"] == "open"
        assert "pending_patch" in data["data"]
        assert "next_step" in data["data"]

    def test_status_json_with_pending_patch(self, tmp_path):
        store = TaskStore(tmp_path)
        store.create("task with patch")
        # Create a fake pending patch file
        (tmp_path / ".sac").mkdir(exist_ok=True)
        (tmp_path / ".sac" / "pending_patch.json").write_text("{}")
        with patch("safecode.cli_status.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["pending_patch"] is True
        assert "sac apply" in data["data"]["next_step"]

    def test_status_json_no_null_error(self, tmp_path):
        with patch("safecode.cli_status.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["status", "--json"])
        data = json.loads(result.output)
        # error key must not be present for success responses
        assert "error" not in data

    def test_status_does_not_write_audit_events(self, tmp_path):
        store = TaskStore(tmp_path)
        store.create("status does not audit")
        audit_log = tmp_path / ".sac" / "logs" / "events.jsonl"
        initial_size = audit_log.stat().st_size if audit_log.exists() else 0
        with patch("safecode.cli_status.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            runner.invoke(app, ["status", "--json"])
        final_size = audit_log.stat().st_size if audit_log.exists() else 0
        assert final_size == initial_size

    def test_status_json_shows_last_test(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("task with test")
        iter_ = TaskIteration(
            iteration_index=0, event="fix",
            test_command="pytest tests/", test_exit_code=1,
        )
        updated = state.model_copy(update={"iterations": [iter_]})
        store.save(updated)
        with patch("safecode.cli_status.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["status", "--json"])
        data = json.loads(result.output)
        assert data["data"]["last_test_command"] == "pytest tests/"
        assert data["data"]["last_test_exit_code"] == 1

    def test_status_json_shows_last_command(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("task with command")
        cmd = TaskCommand(command="git status", exit_code=0)
        updated = state.model_copy(update={"last_command": cmd})
        store.save(updated)
        with patch("safecode.cli_status.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["status", "--json"])
        data = json.loads(result.output)
        assert data["data"]["last_command"] == "git status"

    def test_status_json_envelope(self, tmp_path):
        with patch("safecode.cli_status.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["status", "--json"])
        data = json.loads(result.output)
        assert "command" in data
        assert "status" in data
        assert "data" in data
        assert isinstance(data["data"], dict)
