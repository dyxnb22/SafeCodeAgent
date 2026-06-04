"""Tests for durable SIGINT handling (v4.4.0 T-4.4.0-B)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from safecode.cli import app
from safecode.cli_fix import run_fix, run_fix_watch
from safecode.task.recovery import mark_task_interrupted
from safecode.task.store import TaskStore

runner = CliRunner()


class TestInterruptDurability:
    def test_mark_interrupted_creates_current_task_and_iteration(self, tmp_path):
        state = mark_task_interrupted(tmp_path, command_name="fix", hint="pytest -q")

        assert state is not None
        loaded = TaskStore(tmp_path).load(state.task_id)
        assert loaded is not None
        assert loaded.status == "interrupted"
        assert loaded.iterations[-1].event == "interrupted"
        assert loaded.iterations[-1].failure_category == "interrupted"
        assert TaskStore(tmp_path).current_id() == state.task_id

    def test_sigint_in_fix_marks_interrupted_and_returns_130(self, tmp_path):
        with patch("safecode.cli_fix._run_test_command", side_effect=KeyboardInterrupt):
            code = run_fix(tmp_path, test_command="pytest -q")

        assert code == 130
        state = TaskStore(tmp_path).load(TaskStore(tmp_path).current_id() or "")
        assert state is not None
        assert state.status == "interrupted"
        assert state.iterations[-1].mode == "fix"

    def test_sigint_in_fix_watch_marks_interrupted_and_returns_130(self, tmp_path):
        with patch("safecode.cli_fix._run_test_command", side_effect=KeyboardInterrupt):
            code = run_fix_watch(tmp_path, test_command="pytest -q")

        assert code == 130
        state = TaskStore(tmp_path).load(TaskStore(tmp_path).current_id() or "")
        assert state is not None
        assert state.status == "interrupted"
        assert state.iterations[-1].mode == "fix --watch"

    def test_sigint_in_edit_cli_exits_130(self, tmp_path):
        with (
            patch("safecode.cli_core.Path") as mock_path,
            patch("safecode.cli_core.AgentOrchestrator") as mock_orch,
        ):
            mock_path.cwd.return_value = tmp_path
            mock_orch.return_value.edit.side_effect = KeyboardInterrupt
            result = runner.invoke(app, ["edit", "change file"])

        assert result.exit_code == 130
        assert "resume with: sac resume" in result.output
        state = TaskStore(tmp_path).load(TaskStore(tmp_path).current_id() or "")
        assert state is not None
        assert state.status == "interrupted"

    def test_sigint_in_run_cli_exits_130(self, tmp_path):
        with (
            patch("safecode.cli_core.Path") as mock_path,
            patch("safecode.cli_core.ShellRunner") as mock_runner,
        ):
            mock_path.cwd.return_value = tmp_path
            runner_obj = mock_runner.return_value
            risk = MagicMock()
            risk.level = "low"
            risk.reasons = []
            risk.tokens = ["python"]
            runner_obj.assess.return_value = risk
            runner_obj.run.side_effect = KeyboardInterrupt
            result = runner.invoke(app, ["run", "python -V", "--json"])

        assert result.exit_code == 130
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert "sac resume" in data["error"]
        state = TaskStore(tmp_path).load(TaskStore(tmp_path).current_id() or "")
        assert state is not None
        assert state.status == "interrupted"

    def test_pending_patch_not_corrupted_on_interrupt(self, tmp_path):
        pending = tmp_path / ".sac" / "pending_patch.json"
        pending.parent.mkdir(parents=True, exist_ok=True)
        before = '{"proposal": "keep-me"}\n'
        pending.write_text(before, encoding="utf-8")

        mark_task_interrupted(tmp_path, command_name="edit", hint="manual")

        assert pending.read_text(encoding="utf-8") == before
