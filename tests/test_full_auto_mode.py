"""Tests for v5.1.1 full-auto mode: run_command preview, delay, Ctrl-C abort."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.loop import AgentLoop
from safecode.agent.native_tools import NativeToolCall, NativeToolResult


# ---------------------------------------------------------------------------
# AgentLoop full_auto attribute (v5.1.1)
# ---------------------------------------------------------------------------

class TestAgentLoopFullAuto:
    def test_agent_loop_default_full_auto_false(self, tmp_path):
        loop = AgentLoop(tmp_path)
        assert loop.full_auto is False

    def test_agent_loop_full_auto_true(self, tmp_path):
        loop = AgentLoop(tmp_path, full_auto=True)
        assert loop.full_auto is True

    def test_agent_loop_command_delay_default(self, tmp_path):
        loop = AgentLoop(tmp_path)
        assert loop.command_delay_ms == 500

    def test_agent_loop_command_delay_custom(self, tmp_path):
        loop = AgentLoop(tmp_path, full_auto=True, command_delay_ms=0)
        assert loop.command_delay_ms == 0


# ---------------------------------------------------------------------------
# _build_dispatcher in full-auto mode (v5.1.1)
# ---------------------------------------------------------------------------

class TestFullAutoDispatcher:
    def test_full_auto_approves_write_tools(self, tmp_path):
        """In full-auto mode, write tools are registered with approved=True."""
        (tmp_path / "target.py").write_text("x = 1\n")
        loop = AgentLoop(tmp_path, full_auto=True, command_delay_ms=0)
        dispatcher = loop._build_dispatcher()
        call = NativeToolCall(
            tool_name="edit_file",
            input={"path": "target.py", "old_string": "x = 1\n", "new_string": "x = 2\n"},
            call_id="c1",
        )
        result = dispatcher.dispatch(call)
        assert result.status == "success"

    def test_full_auto_command_tool_has_delay_zero(self, tmp_path, capsys):
        """run_command in full-auto mode with delay=0 prints preview but doesn't sleep."""
        loop = AgentLoop(tmp_path, full_auto=True, command_delay_ms=0)
        dispatcher = loop._build_dispatcher()

        # Mock ShellRunner.run to avoid actually running a command
        mock_result = MagicMock()
        mock_result.executed = True
        mock_result.exit_code = 0
        mock_result.stdout = "hello"
        mock_result.stderr = ""
        mock_result.duration_ms = 10

        with patch("safecode.shell.runner.ShellRunner.run", return_value=mock_result):
            call = NativeToolCall(
                tool_name="run_command",
                input={"command": "echo hello"},
                call_id="c2",
            )
            result = dispatcher.dispatch(call)

        assert result.status == "success"
        captured = capsys.readouterr()
        assert "→ run_command" in captured.out
        assert "echo hello" in captured.out
        assert "exit 0" in captured.out


# ---------------------------------------------------------------------------
# High-risk command still blocked in full-auto (v5.1.1)
# ---------------------------------------------------------------------------

class TestHighRiskStillBlockedInFullAuto:
    def test_high_risk_command_blocked(self, tmp_path):
        """High-risk commands must still be blocked even in full-auto mode."""
        loop = AgentLoop(tmp_path, full_auto=True, command_delay_ms=0)
        dispatcher = loop._build_dispatcher()

        # ShellRunner will block rm -rf / as high-risk
        call = NativeToolCall(
            tool_name="run_command",
            input={"command": "rm -rf /"},
            call_id="c3",
        )
        result = dispatcher.dispatch(call)
        # Should be blocked or error (ShellRunner classifies rm -rf / as high_risk)
        assert result.status in {"blocked", "error"}


# ---------------------------------------------------------------------------
# Ctrl-C aborts command in full-auto delay
# ---------------------------------------------------------------------------

class TestFullAutoCtrlCAbort:
    def test_ctrl_c_during_delay_returns_blocked(self, tmp_path):
        """KeyboardInterrupt during the full-auto delay returns status=blocked."""
        from safecode.agent.command_tool import _run_command_handler

        import time
        original_sleep = time.sleep

        def _raise_on_sleep(seconds):
            raise KeyboardInterrupt

        with patch("time.sleep", side_effect=_raise_on_sleep):
            result = _run_command_handler("c4", {
                "_project_root": str(tmp_path),
                "command": "echo hello",
                "_full_auto_delay_ms": 500,
            })

        assert result.status == "blocked"
        assert "aborted" in (result.error or "").lower() or result.metadata.get("aborted") is True


# ---------------------------------------------------------------------------
# Command preview line format (v5.1.1)
# ---------------------------------------------------------------------------

class TestCommandPreviewFormat:
    def test_preview_line_printed_before_execution(self, tmp_path, capsys):
        """In full-auto mode, a preview line is printed before the command runs."""
        from safecode.agent.command_tool import _run_command_handler

        mock_result = MagicMock()
        mock_result.executed = True
        mock_result.exit_code = 0
        mock_result.stdout = "ok"
        mock_result.stderr = ""
        mock_result.duration_ms = 5

        with patch("safecode.shell.runner.ShellRunner.run", return_value=mock_result):
            _run_command_handler("c5", {
                "_project_root": str(tmp_path),
                "command": "pytest -q",
                "_full_auto_delay_ms": 0,
            })

        captured = capsys.readouterr()
        assert "→ run_command  pytest -q" in captured.out

    def test_exit_code_line_printed_after_execution(self, tmp_path, capsys):
        """Exit code line is printed after execution."""
        from safecode.agent.command_tool import _run_command_handler

        mock_result = MagicMock()
        mock_result.executed = True
        mock_result.exit_code = 1
        mock_result.stdout = ""
        mock_result.stderr = "fail"
        mock_result.duration_ms = 10

        with patch("safecode.shell.runner.ShellRunner.run", return_value=mock_result):
            _run_command_handler("c6", {
                "_project_root": str(tmp_path),
                "command": "false",
                "_full_auto_delay_ms": 0,
            })

        captured = capsys.readouterr()
        assert "exit 1" in captured.out


# ---------------------------------------------------------------------------
# Full-auto mode via CLI shell flags (v5.1.1)
# ---------------------------------------------------------------------------

class TestFullAutoCLIFlags:
    def test_shell_full_auto_flag_passes_to_agentic_shell(self, tmp_path, monkeypatch):
        """--full-auto flag is passed to _run_agentic_shell."""
        from typer.testing import CliRunner
        from safecode.cli import app
        from safecode.agent.session import AgentSessionState
        from safecode.agent.loop import AgentRunResult
        from safecode.utils.time import utc_now_iso

        monkeypatch.chdir(tmp_path)
        captured = {}

        class FakeLoop:
            def __init__(self, project_root, llm_client=None, *, auto_edit=False,
                         full_auto=False, command_delay_ms=500, no_clarify=False,
                         plan_mode=False):
                captured["full_auto"] = full_auto
                captured["command_delay_ms"] = command_delay_ms
                self._native_write_count = 0

            def session_cost(self):
                return None

            def run(self, goal, max_steps=8, *, on_step=None, conversation=None):
                state = AgentSessionState(
                    session_id="fa-sess",
                    goal=goal or "",
                    plan=[],
                    current_step=0,
                    status="completed",
                    pending_action=None,
                    last_observation="done",
                    last_error=None,
                    created_at=utc_now_iso(),
                    updated_at=utc_now_iso(),
                )
                return AgentRunResult(state=state, steps=[], stopped_reason="completed")

            @property
            def last_typed_result(self):
                return None

        with patch("safecode.cli_shell.AgentLoop", FakeLoop):
            result = CliRunner().invoke(
                app, ["shell", "--full-auto", "--non-tty", "--command-delay-ms", "0"],
                input="run the tests\n",
            )

        assert result.exit_code == 0, result.output
        assert captured.get("full_auto") is True
        assert captured.get("command_delay_ms") == 0

    def test_command_delay_ms_clamped_to_2000(self, tmp_path, monkeypatch):
        """--command-delay-ms is clamped to [0, 2000]."""
        from typer.testing import CliRunner
        from safecode.cli import app
        from safecode.agent.session import AgentSessionState
        from safecode.agent.loop import AgentRunResult
        from safecode.utils.time import utc_now_iso

        monkeypatch.chdir(tmp_path)
        captured = {}

        class FakeLoop:
            def __init__(self, project_root, llm_client=None, *, auto_edit=False,
                         full_auto=False, command_delay_ms=500, no_clarify=False,
                         plan_mode=False):
                captured["command_delay_ms"] = command_delay_ms
                self._native_write_count = 0

            def session_cost(self):
                return None

            def run(self, goal, max_steps=8, *, on_step=None, conversation=None):
                state = AgentSessionState(
                    session_id="fa-sess2",
                    goal=goal or "",
                    plan=[],
                    current_step=0,
                    status="completed",
                    pending_action=None,
                    last_observation="done",
                    last_error=None,
                    created_at=utc_now_iso(),
                    updated_at=utc_now_iso(),
                )
                return AgentRunResult(state=state, steps=[], stopped_reason="completed")

            @property
            def last_typed_result(self):
                return None

        with patch("safecode.cli_shell.AgentLoop", FakeLoop):
            CliRunner().invoke(
                app, ["shell", "--full-auto", "--non-tty", "--command-delay-ms", "9999"],
                input="test\n",
            )

        assert captured.get("command_delay_ms") == 2000
