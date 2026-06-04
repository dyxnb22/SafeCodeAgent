"""Tests for sac task CLI subcommands (v4.1.0 T-4.1.0-B)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.task.store import TaskStore

runner = CliRunner()


def _store(tmp_path: Path) -> TaskStore:
    return TaskStore(tmp_path)


# ---------------------------------------------------------------------------
# sac task new
# ---------------------------------------------------------------------------

class TestTaskNew:
    def test_creates_task_and_prints_id(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "new", "Fix the login flow"])
        assert result.exit_code == 0
        assert "Task created:" in result.output

    def test_creates_task_json_output(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "new", "Add /health route", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["command"] == "task new"
        assert data["status"] == "success"
        assert "task_id" in data["data"]
        assert "goal" in data["data"]

    def test_empty_goal_error(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "new", "  "])
        assert result.exit_code != 0

    def test_empty_goal_json_error(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "new", "  ", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert "error" in data

    def test_sets_current(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            runner.invoke(app, ["task", "new", "A task"])
        store = _store(tmp_path)
        assert store.current_id() is not None


# ---------------------------------------------------------------------------
# sac task list
# ---------------------------------------------------------------------------

class TestTaskList:
    def test_empty_list(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "list"])
        assert result.exit_code == 0
        assert "No tasks found" in result.output

    def test_list_json_empty(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["count"] == 0
        assert data["data"]["tasks"] == []

    def test_list_shows_tasks(self, tmp_path):
        store = _store(tmp_path)
        store.create("first task")
        store.create("second task")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["count"] == 2

    def test_list_deterministic_json(self, tmp_path):
        store = _store(tmp_path)
        store.create("first")
        store.create("second")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            r1 = runner.invoke(app, ["task", "list", "--json"])
            r2 = runner.invoke(app, ["task", "list", "--json"])
        assert r1.output == r2.output

    def test_list_marks_current(self, tmp_path):
        store = _store(tmp_path)
        s1 = store.create("task one")
        s2 = store.create("task two")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "list", "--json"])
        data = json.loads(result.output)
        items = data["data"]["tasks"]
        current_items = [i for i in items if i["current"]]
        assert len(current_items) == 1
        assert current_items[0]["task_id"] == s2.task_id


# ---------------------------------------------------------------------------
# sac task show
# ---------------------------------------------------------------------------

class TestTaskShow:
    def test_show_current(self, tmp_path):
        store = _store(tmp_path)
        state = store.create("show me this task")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "show"])
        assert result.exit_code == 0
        assert state.task_id in result.output

    def test_show_by_id(self, tmp_path):
        store = _store(tmp_path)
        state = store.create("specific task")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "show", state.task_id])
        assert result.exit_code == 0
        assert state.task_id in result.output

    def test_show_json(self, tmp_path):
        store = _store(tmp_path)
        state = store.create("json show")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "show", state.task_id, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["data"]["task_id"] == state.task_id

    def test_show_nonexistent_error(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "show", "no-such-task"])
        assert result.exit_code != 0

    def test_show_no_current_error(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "show"])
        assert result.exit_code != 0

    def test_show_redacts_secrets(self, tmp_path):
        store = _store(tmp_path)
        # A GitHub token pattern is recognised by redact_secrets
        token = "ghp_abcdefghijklmnop1234567890abcdef"
        state = store.create(f"task goal with token {token} here")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "show", state.task_id, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Goal should be redacted via redact_secrets (token replaced with [REDACTED])
        assert token not in data["data"].get("goal", "")


# ---------------------------------------------------------------------------
# sac task switch
# ---------------------------------------------------------------------------

class TestTaskSwitch:
    def test_switch_changes_current(self, tmp_path):
        store = _store(tmp_path)
        s1 = store.create("task one")
        _s2 = store.create("task two")
        # Now CURRENT is s2; switch to s1
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "switch", s1.task_id])
        assert result.exit_code == 0
        assert store.current_id() == s1.task_id

    def test_switch_nonexistent_error(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "switch", "no-such-task"])
        assert result.exit_code != 0

    def test_switch_json(self, tmp_path):
        store = _store(tmp_path)
        s1 = store.create("json switch task")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "switch", s1.task_id, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["data"]["task_id"] == s1.task_id


# ---------------------------------------------------------------------------
# sac task close
# ---------------------------------------------------------------------------

class TestTaskClose:
    def test_close_current_task(self, tmp_path):
        store = _store(tmp_path)
        state = store.create("to close")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "close"])
        assert result.exit_code == 0
        loaded = store.load(state.task_id)
        assert loaded is not None
        assert loaded.status == "closed"

    def test_close_by_id(self, tmp_path):
        store = _store(tmp_path)
        state = store.create("close by id")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "close", state.task_id])
        assert result.exit_code == 0

    def test_close_json(self, tmp_path):
        store = _store(tmp_path)
        state = store.create("close json")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "close", state.task_id, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["data"]["status"] == "closed"


# ---------------------------------------------------------------------------
# sac task delete
# ---------------------------------------------------------------------------

class TestTaskDelete:
    def test_delete_requires_yes(self, tmp_path):
        store = _store(tmp_path)
        state = store.create("to delete")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "delete", state.task_id])
        # Should fail without --yes
        assert result.exit_code != 0
        # Task should still exist
        assert store.load(state.task_id) is not None

    def test_delete_with_yes(self, tmp_path):
        store = _store(tmp_path)
        state = store.create("delete me")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "delete", state.task_id, "--yes"])
        assert result.exit_code == 0
        assert store.load(state.task_id) is None

    def test_delete_json(self, tmp_path):
        store = _store(tmp_path)
        state = store.create("json delete")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "delete", state.task_id, "--yes", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["data"]["deleted"] is True

    def test_delete_requires_yes_json(self, tmp_path):
        store = _store(tmp_path)
        state = store.create("no yes delete")
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "delete", state.task_id, "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert "error" in data

    def test_delete_nonexistent(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "delete", "no-such-task", "--yes"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# JSON envelope contract compliance
# ---------------------------------------------------------------------------

class TestJSONEnvelopeCompliance:
    """All --json outputs must conform to CLIJSONResponse contract (stable contract 11)."""

    def _assert_envelope(self, raw: str) -> dict:
        data = json.loads(raw)
        assert "command" in data
        assert "status" in data
        assert "data" in data
        assert isinstance(data["data"], dict)
        if "error" in data:
            assert isinstance(data["error"], str)
        return data

    def test_new_envelope(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "new", "envelope test", "--json"])
        self._assert_envelope(result.output)

    def test_list_envelope(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "list", "--json"])
        self._assert_envelope(result.output)

    def test_delete_error_no_null_error_field(self, tmp_path):
        with patch("safecode.cli_task.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["task", "delete", "x", "--json"])
        data = json.loads(result.output)
        # When status=error, error key present; when success, error key absent
        assert data["status"] == "error"
        assert "error" in data
