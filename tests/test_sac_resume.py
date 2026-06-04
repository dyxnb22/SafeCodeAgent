"""Tests for sac resume (v4.4.0 T-4.4.0-A)."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.cli import app
from safecode.task.state import TaskCommand, TaskIteration
from safecode.task.store import TaskStore

runner = CliRunner()


def _invoke(tmp_path, args):
    with patch("safecode.cli_resume.Path") as mock_path:
        mock_path.cwd.return_value = tmp_path
        return runner.invoke(app, args)


class TestSacResume:
    def test_resume_current_task(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("finish docs")

        result = _invoke(tmp_path, ["resume", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["command"] == "resume"
        assert data["status"] == "success"
        assert data["data"]["task_id"] == state.task_id
        assert TaskStore(tmp_path).current_id() == state.task_id

    def test_resume_explicit_task(self, tmp_path):
        store = TaskStore(tmp_path)
        first = store.create("first")
        second = store.create("second")

        result = _invoke(tmp_path, ["resume", first.task_id, "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["task_id"] == first.task_id
        assert data["data"]["task_id"] != second.task_id
        assert TaskStore(tmp_path).current_id() == first.task_id

    def test_resume_refuses_closed_task(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("done")
        store.save(state.model_copy(update={"status": "closed"}))

        result = _invoke(tmp_path, ["resume", state.task_id, "--json"])

        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert "closed" in data["error"]

    def test_no_open_task_message(self, tmp_path):
        result = _invoke(tmp_path, ["resume", "--json"])

        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "sac task new" in data["error"]
        assert "next_step" in data["data"]

    def test_resume_uses_most_recent_open_or_interrupted_when_current_missing(self, tmp_path):
        store = TaskStore(tmp_path)
        old = store.create("old")
        new = store.create("new")
        store.clear_current()

        result = _invoke(tmp_path, ["resume", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["task_id"] == new.task_id
        assert data["data"]["task_id"] != old.task_id

    def test_interrupted_task_reopens_on_resume(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("resume me")
        store.save(state.model_copy(update={"status": "interrupted"}))

        result = _invoke(tmp_path, ["resume", "--json"])

        assert result.exit_code == 0
        assert TaskStore(tmp_path).load(state.task_id).status == "open"  # type: ignore[union-attr]

    def test_resume_output_is_redacted(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("fix token=s3cr3t")
        iteration = TaskIteration(
            iteration_index=0,
            event="fix",
            test_command="pytest --password hunter2",
            test_exit_code=1,
            status="failed",
        )
        updated = state.model_copy(
            update={
                "last_command": TaskCommand(command="echo api_key=abc123"),
                "iterations": [iteration],
            }
        )
        store.save(updated)

        result = _invoke(tmp_path, ["resume"])

        assert result.exit_code == 0
        assert "s3cr3t" not in result.output
        assert "hunter2" not in result.output
        assert "abc123" not in result.output
        assert "next_step" in result.output

    def test_resume_json_shape_contains_safe_summary(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("with patch")
        (tmp_path / ".sac").mkdir(exist_ok=True)
        (tmp_path / ".sac" / "pending_patch.json").write_text('{"kept": true}', encoding="utf-8")

        result = _invoke(tmp_path, ["resume", state.task_id, "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["pending_patch"]["exists"] is True
        assert "sac apply" in data["next_step"]
        assert data["last_fix_iteration"] is None
