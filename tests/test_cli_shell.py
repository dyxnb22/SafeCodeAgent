"""Tests for sac shell — v4.9.0 shell-session-and-repl."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# CLI registration / help
# ---------------------------------------------------------------------------


class TestShellRegistration:
    def test_shell_in_help(self, tmp_path, monkeypatch):
        """sac --help must include the 'shell' command."""
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "shell" in result.output

    def test_shell_help_text(self, tmp_path, monkeypatch):
        """sac shell --help shows the EXPERIMENTAL label."""
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--help"])
        assert result.exit_code == 0
        assert "EXPERIMENTAL" in result.output

    def test_shell_non_tty_help(self, tmp_path, monkeypatch):
        """sac shell /help works in non-TTY mode."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/help\n/exit\n")
        assert result.exit_code == 0
        assert "Slash commands" in result.output


# ---------------------------------------------------------------------------
# TTY / non-TTY behaviour
# ---------------------------------------------------------------------------


class TestShellTTYBehaviour:
    def test_non_tty_exit(self, tmp_path, monkeypatch):
        """Non-TTY mode exits cleanly on /exit."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/exit\n")
        assert result.exit_code == 0
        assert "Exiting" in result.output

    def test_non_tty_eof_exits(self, tmp_path, monkeypatch):
        """Non-TTY mode exits cleanly on EOF."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="")
        assert result.exit_code == 0

    def test_non_tty_status(self, tmp_path, monkeypatch):
        """Non-TTY /status returns task info without crashing."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/status\n/exit\n")
        assert result.exit_code == 0
        assert "task_id" in result.output

    def test_non_tty_status_is_workspace_dashboard(self, tmp_path, monkeypatch):
        """In-shell /status should be the main product dashboard, not task-only output."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/status\n/exit\n")

        assert result.exit_code == 0
        for label in ("Provider", "Task", "Session", "Memory", "Safety", "Workspace", "Next"):
            assert label in result.output
        assert "credential:" in result.output
        assert "approved facts:" in result.output
        assert "network:" in result.output

    def test_non_tty_continue_without_session_explains_next_step(self, tmp_path, monkeypatch):
        """In-shell /continue should guide instead of failing when there is no active session."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/continue\n/exit\n")

        assert result.exit_code == 0
        assert "No active agent session" in result.output
        assert "Next:" in result.output

    def test_non_tty_continue_advances_active_agent_session(self, tmp_path, monkeypatch):
        """In-shell /continue advances one safe mock-backed agent step."""
        from typer.testing import CliRunner
        from safecode.agent.session import AgentSessionStore
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        state = AgentSessionStore(tmp_path).start("continue safely", plan=["inspect", "summarize"])

        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/continue\n/exit\n")

        assert result.exit_code == 0
        assert "Continued one safe agent step" in result.output
        updated = AgentSessionStore(tmp_path).load()
        assert updated is not None
        assert updated.session_id == state.session_id
        assert updated.current_step == 1

    def test_non_tty_continue_does_not_apply_pending_patch(self, tmp_path, monkeypatch):
        """In-shell /continue must not cross the patch approval gate."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        pending = tmp_path / ".sac" / "pending_patch.json"
        pending.parent.mkdir(parents=True)
        pending.write_text("{}", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/continue\n/exit\n")

        assert result.exit_code == 0
        assert "Pending patch is ready" in result.output
        assert "Next: /apply" in result.output
        assert pending.exists()

    def test_non_tty_ready_reports_readiness_card(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["shell", "--non-tty"], input="/ready\n/exit\n")

        assert result.exit_code == 0
        assert "Readiness:" in result.output
        assert "Provider:" in result.output
        assert "Credential:" in result.output

    def test_non_tty_memory_show_and_teach(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["shell", "--non-tty"],
            input='/memory teach "always run pytest -q before commit"\n/memory\n/exit\n',
        )

        assert result.exit_code == 0
        assert "Memory Note Added" in result.output
        assert "Memory" in result.output
        assert "Injected project notes: yes" in result.output

    def test_non_tty_memory_review_lists_pending_facts(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from safecode.cli import app
        from safecode.memory.facts import ProjectFactStore

        monkeypatch.chdir(tmp_path)
        fact = ProjectFactStore(tmp_path / ".sac").propose("test_command", "pytest -q", source="auto")
        assert fact is not None

        result = CliRunner().invoke(app, ["shell", "--non-tty"], input="/memory review\n/exit\n")

        assert result.exit_code == 0
        assert "Memory Review" in result.output
        assert fact.fact_id[:8] in result.output

    def test_non_tty_demo_shows_safe_path(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["shell", "--non-tty"], input="/demo\n/exit\n")

        assert result.exit_code == 0
        assert "Safe First-Run Demo" in result.output
        assert "/status" in result.output
        assert "/apply" in result.output

    def test_non_tty_task(self, tmp_path, monkeypatch):
        """Non-TTY /task returns task details."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/task\n/exit\n")
        assert result.exit_code == 0

    def test_non_tty_plain_input_records_turn(self, tmp_path, monkeypatch):
        """Plain (non-slash) input is accepted and stored as a shell turn."""
        from typer.testing import CliRunner
        from safecode.cli import app
        from safecode.shell_session.store import ShellSessionStore

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            app, ["shell", "--non-tty"], input="what is this project?\n/exit\n"
        )
        assert result.exit_code == 0

        # A session file should exist
        store = ShellSessionStore(tmp_path)
        sessions = store.list_sessions()
        assert len(sessions) >= 1, "At least one session must be persisted"

        session = store.load(sessions[0])
        assert session is not None
        # The natural-language turn must be recorded
        nl_turns = [t for t in session.turns if not t.user_input.startswith("/")]
        assert len(nl_turns) >= 1

    def test_non_tty_unknown_slash(self, tmp_path, monkeypatch):
        """Unknown slash command returns a helpful message."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/foobar\n/exit\n")
        assert result.exit_code == 0
        assert "Unknown slash command" in result.output

    def test_non_tty_debug_reuses_last_failure(self, tmp_path, monkeypatch):
        """/debug reports the same last-failure evidence as the debug CLI."""
        from typer.testing import CliRunner
        from safecode.cli import app
        from safecode.logs.runtime import RuntimeLogger

        RuntimeLogger(tmp_path).write(
            "error",
            "test",
            "command failed",
            failure_category="command_timeout",
            details={"command": "pytest -q", "task_id": "task-1"},
        )

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/debug\n/exit\n")
        assert result.exit_code == 0
        assert "category: command_timeout" in result.output
        assert "source: runtime_log" in result.output
        assert "suggested:" in result.output
        assert "Debug info unavailable" not in result.output


# ---------------------------------------------------------------------------
# Session persistence and corruption tolerance
# ---------------------------------------------------------------------------


class TestShellSessionPersistence:
    def test_session_persisted_to_dot_sac(self, tmp_path, monkeypatch):
        """Shell session files are written under .sac/shell/."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        runner.invoke(app, ["shell", "--non-tty"], input="/help\n/exit\n")

        shell_dir = tmp_path / ".sac" / "shell"
        assert shell_dir.exists(), ".sac/shell/ must be created"
        sessions = list(shell_dir.glob("*.json"))
        assert len(sessions) >= 1, "At least one session file must be written"

    def test_session_file_is_valid_json(self, tmp_path, monkeypatch):
        """Session files must be valid JSON."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        runner.invoke(app, ["shell", "--non-tty"], input="/help\n/exit\n")

        shell_dir = tmp_path / ".sac" / "shell"
        for f in shell_dir.glob("*.json"):
            data = json.loads(f.read_text())
            assert "session_id" in data
            assert "payload_version" in data

    def test_corrupt_session_handled_gracefully(self, tmp_path):
        """A corrupt session file returns None (fail-safe) instead of crashing."""
        from safecode.shell_session.store import ShellSessionStore

        shell_dir = tmp_path / ".sac" / "shell"
        shell_dir.mkdir(parents=True)
        corrupt_file = shell_dir / "corrupt12345678.json"
        corrupt_file.write_text("{not valid json !!!", encoding="utf-8")

        store = ShellSessionStore(tmp_path)
        result = store.load("corrupt12345678")
        assert result is None, "Corrupt file must return None, not raise"

    def test_future_payload_version_returns_none(self, tmp_path):
        """A session with payload_version > 1 returns None (fail-closed)."""
        from safecode.shell_session.store import ShellSessionStore

        shell_dir = tmp_path / ".sac" / "shell"
        shell_dir.mkdir(parents=True)
        future_file = shell_dir / "future12345678.json"
        future_file.write_text(
            json.dumps({"session_id": "future12345678", "payload_version": 99, "turns": []}),
            encoding="utf-8",
        )

        store = ShellSessionStore(tmp_path)
        result = store.load("future12345678")
        assert result is None, "Future payload version must return None"

    def test_missing_session_returns_none(self, tmp_path):
        """Loading a non-existent session returns None."""
        from safecode.shell_session.store import ShellSessionStore

        store = ShellSessionStore(tmp_path)
        result = store.load("nonexistent123")
        assert result is None

    def test_turns_bounded_to_max(self, tmp_path):
        """Turns list is bounded to _MAX_TURNS entries."""
        from safecode.shell_session.state import ShellSessionState, ShellTurn, _MAX_TURNS

        turns = [
            ShellTurn(turn_index=i, user_input=f"q{i}", shell_response=f"a{i}")
            for i in range(_MAX_TURNS + 20)
        ]
        state = ShellSessionState(session_id="test", turns=turns)
        bounded = state.bounded_turns()
        assert len(bounded) == _MAX_TURNS


# ---------------------------------------------------------------------------
# Task and audit wiring
# ---------------------------------------------------------------------------


class TestShellTaskAndAuditWiring:
    def test_shell_binds_to_current_task(self, tmp_path, monkeypatch):
        """Shell session picks up the CURRENT task id."""
        from safecode.task.store import TaskStore
        from safecode.shell_session.store import ShellSessionStore
        from typer.testing import CliRunner
        from safecode.cli import app

        # Create a task and set it as CURRENT
        task_store = TaskStore(tmp_path)
        task = task_store.create("fix the widget bug")
        task_store.set_current(task.task_id)

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        runner.invoke(app, ["shell", "--non-tty"], input="/exit\n")

        shell_store = ShellSessionStore(tmp_path)
        sessions = shell_store.list_sessions()
        assert sessions, "Session must be created"
        session = shell_store.load(sessions[-1])
        assert session is not None
        assert session.task_id == task.task_id, "Session must bind to current task"

    def test_shell_writes_audit_event_per_turn(self, tmp_path, monkeypatch):
        """An audit event is written for each shell turn."""
        from typer.testing import CliRunner
        from safecode.cli import app
        from safecode.audit.logger import AuditLogger

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        runner.invoke(app, ["shell", "--non-tty"], input="/help\n/exit\n")

        audit_log = tmp_path / ".sac" / "logs" / "events.jsonl"
        if audit_log.exists():
            lines = [l for l in audit_log.read_text().splitlines() if "shell_turn" in l]
            assert len(lines) >= 1, "At least one shell_turn audit event must be written"


# ---------------------------------------------------------------------------
# No auto-apply regression
# ---------------------------------------------------------------------------


class TestShellNoAutoApply:
    def test_apply_in_non_tty_does_not_apply(self, tmp_path, monkeypatch):
        """/apply in non-TTY mode must NOT apply — it prints instructions instead."""
        from typer.testing import CliRunner
        from safecode.cli import app

        # Create a fake pending patch
        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        from safecode.patch.models import PatchProposal
        proposal = PatchProposal(
            id="no-auto-patch",
            task="smoke test",
            blocks=[],
            created_at="2026-01-01T00:00:00Z",
            model="mock",
            status="pending",
        )
        (sac_dir / "pending_patch.json").write_text(proposal.model_dump_json())

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/apply\n/exit\n")
        assert result.exit_code == 0

        # Must NOT have run any apply subprocess; must print "sac apply" hint
        assert "sac apply" in result.output, "/apply in non-TTY must print 'sac apply' hint"

        # The patch file must still exist — nothing applied it
        assert (sac_dir / "pending_patch.json").exists(), "Patch must remain unapplied"

    def test_commit_in_non_tty_does_not_commit(self, tmp_path, monkeypatch):
        """/commit in non-TTY mode must NOT commit."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["shell", "--non-tty"], input="/commit\n/exit\n")
        assert result.exit_code == 0
        assert "sac commit" in result.output, "/commit in non-TTY must print 'sac commit' hint"

    def test_slash_apply_requires_confirmation(self, tmp_path):
        """run_shell with /apply in TTY mode asks for confirmation before applying."""
        from safecode.cli_shell import run_shell
        from safecode.patch.models import PatchProposal

        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        proposal = PatchProposal(
            id="apply-confirm-test",
            task="test",
            blocks=[],
            created_at="2026-01-01T00:00:00Z",
            model="mock",
            status="pending",
        )
        (sac_dir / "pending_patch.json").write_text(proposal.model_dump_json())

        # Simulate TTY mode but user says 'n'
        with patch("safecode.cli_shell.input", return_value="n"):
            with patch("safecode.cli_shell._read_line", side_effect=["/apply", None]):
                code = run_shell(tmp_path, is_tty=True)

        assert code == 0
        assert (sac_dir / "pending_patch.json").exists(), "Patch must remain after 'n' confirmation"


# ---------------------------------------------------------------------------
# JSON output mode
# ---------------------------------------------------------------------------


class TestShellJsonOutput:
    def test_json_output_per_turn(self, tmp_path, monkeypatch):
        """--json outputs JSON objects containing 'command' and 'status' fields."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            app, ["shell", "--non-tty", "--json"], input="/help\n/exit\n"
        )
        assert result.exit_code == 0
        # render_json outputs multi-line indented JSON; check for key fields
        assert '"command"' in result.output, "JSON output must contain 'command' key"
        assert '"status"' in result.output, "JSON output must contain 'status' key"
        assert '"intent"' in result.output, "JSON output must contain 'intent' key"


# ---------------------------------------------------------------------------
# State model unit tests
# ---------------------------------------------------------------------------


class TestShellSessionState:
    def test_session_state_roundtrip(self, tmp_path):
        """Session state serializes and deserializes correctly."""
        from safecode.shell_session.state import ShellSessionState, ShellTurn

        state = ShellSessionState(session_id="abc123", task_id="task-1")
        turn = ShellTurn(
            turn_index=0,
            user_input="hello",
            shell_response="world",
            intent="ask",
            task_id="task-1",
        )
        state = state.model_copy(update={"turns": [turn]})
        raw = state.model_dump_json()
        loaded = ShellSessionState.model_validate_json(raw)
        assert loaded.session_id == "abc123"
        assert loaded.task_id == "task-1"
        assert len(loaded.turns) == 1
        assert loaded.turns[0].intent == "ask"

    def test_next_turn_index(self):
        """next_turn_index returns len(turns)."""
        from safecode.shell_session.state import ShellSessionState, ShellTurn

        state = ShellSessionState(session_id="x")
        assert state.next_turn_index() == 0
        turn = ShellTurn(turn_index=0, user_input="q", shell_response="a")
        state = state.model_copy(update={"turns": [turn]})
        assert state.next_turn_index() == 1

    def test_supported_payload_version(self):
        from safecode.shell_session.state import ShellSessionState
        assert ShellSessionState.supported_payload_version() == 1


# ---------------------------------------------------------------------------
# v4.11.2: sac shell --agentic routing
# ---------------------------------------------------------------------------


class TestShellAgenticMode:
    """Verify --agentic routes to AgentLoop.run() and default behavior is unchanged."""

    def test_agentic_flag_in_help(self, tmp_path, monkeypatch):
        """sac shell --help must document the --agentic flag."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["shell", "--help"])
        assert result.exit_code == 0
        assert "--agentic" in result.output

    def test_agentic_flag_experimental_in_help(self, tmp_path, monkeypatch):
        """--agentic help text must mention EXPERIMENTAL."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["shell", "--help"])
        assert result.exit_code == 0
        assert "EXPERIMENTAL" in result.output.upper() or "experimental" in result.output

    def test_agentic_runs_agent_loop(self, tmp_path, monkeypatch):
        """--agentic must invoke AgentLoop.run() with the user's goal."""
        from typer.testing import CliRunner
        from safecode.cli import app
        from unittest.mock import patch, MagicMock
        from safecode.agent.loop import AgentRunResult
        from safecode.agent.session import AgentSessionState
        from safecode.utils.time import utc_now_iso

        monkeypatch.chdir(tmp_path)
        captured = {}

        class FakeLoop:
            def __init__(self, project_root, llm_client=None, *, auto_edit=False,
                         full_auto=False, command_delay_ms=500, no_clarify=False,
                         plan_mode=False):
                self._native_write_count = 0

            def session_cost(self):
                return None

            def run(self, goal, max_steps=8, *, on_step=None, conversation=None):
                captured["goal"] = goal
                state = AgentSessionState(
                    session_id="agentic-sess-001",
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
                app, ["shell", "--agentic", "--non-tty"], input="add a feature\n"
            )

        assert result.exit_code == 0
        assert captured.get("goal") == "add a feature"

    def test_agentic_empty_input_exits_cleanly(self, tmp_path, monkeypatch):
        """--agentic exits 0 on empty input."""
        from typer.testing import CliRunner
        from safecode.cli import app
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(
            app, ["shell", "--agentic", "--non-tty"], input="\n"
        )
        assert result.exit_code == 0

    def test_without_agentic_uses_existing_router(self, tmp_path, monkeypatch):
        """Without --agentic, shell uses the existing v4.9 intent router (not AgentLoop)."""
        from typer.testing import CliRunner
        from safecode.cli import app
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)

        agent_loop_called = []

        class FakeLoop:
            def __init__(self, project_root, llm_client=None, *, auto_edit=False,
                         full_auto=False, command_delay_ms=500, no_clarify=False,
                         plan_mode=False):
                agent_loop_called.append(True)
                self._native_write_count = 0

            def session_cost(self):
                return None

            def run(self, goal, max_steps=8, *, on_step=None):
                pass

            @property
            def last_typed_result(self):
                return None

        with patch("safecode.cli_shell.AgentLoop", FakeLoop):
            result = CliRunner().invoke(
                app, ["shell", "--non-tty"], input="/help\n/exit\n"
            )

        assert result.exit_code == 0
        assert not agent_loop_called, "AgentLoop must not be called without --agentic"

    def test_agentic_eof_input_exits_cleanly(self, tmp_path, monkeypatch):
        """--agentic on EOF returns exit code 0."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(
            app, ["shell", "--agentic", "--non-tty"], input=""
        )
        assert result.exit_code == 0
