"""Tests for v7.0.4 session timeline and resume views."""

from __future__ import annotations

from typer.testing import CliRunner

from safecode.agent.session import AgentSessionStore
from safecode.cli import app
from safecode.cli_shell import _SLASH_COMMANDS, _handle_slash_command
from safecode.report.session_timeline import build_session_timeline, render_session_timeline
from safecode.state.journal import AgentJournalStore


runner = CliRunner()


def test_session_timeline_projection_from_journal(tmp_path) -> None:
    state = AgentSessionStore(tmp_path).start("timeline goal", plan=["inspect", "summarize"])
    AgentJournalStore(tmp_path).record_command(
        state.session_id,
        "validation suite test exited 0",
        {"command": ["pytest", "-q"], "exit_code": 0, "executed": True},
    )

    rows = build_session_timeline(tmp_path, state.session_id)
    text = render_session_timeline(tmp_path, state.session_id)

    assert rows[0].kind == "plan"
    assert any(row.kind == "command" for row in rows)
    assert "timeline goal" in text or "Planned" in text
    assert "pytest -q" in text


def test_session_show_timeline_cli(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    state = AgentSessionStore(tmp_path).start("show timeline", plan=["inspect"])

    result = runner.invoke(app, ["session", "show", state.session_id, "--timeline"])

    assert result.exit_code == 0
    assert "Session timeline" in result.output
    assert state.session_id in result.output


def test_session_resume_cli_passively_resumes_from_journal(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    state = AgentSessionStore(tmp_path).start("resume timeline", plan=["inspect"])

    result = runner.invoke(app, ["session", "resume", state.session_id, "--json"])

    assert result.exit_code == 0
    assert state.session_id in result.output
    assert "\"status\": \"active\"" in result.output


def test_shell_new_session_slash_commands(tmp_path) -> None:
    for command in ("/timeline", "/sessions", "/resume"):
        assert command in _SLASH_COMMANDS

    state = AgentSessionStore(tmp_path).start("slash timeline", plan=["inspect"])

    timeline, intent, exit_shell = _handle_slash_command("/timeline", tmp_path, None, is_tty=False)
    assert intent == "timeline"
    assert exit_shell is False
    assert state.session_id in timeline

    sessions, intent, _ = _handle_slash_command("/sessions", tmp_path, None, is_tty=False)
    assert intent == "sessions"
    assert state.session_id in sessions

    resumed, intent, _ = _handle_slash_command(f"/resume {state.session_id}", tmp_path, None, is_tty=False)
    assert intent == "resume"
    assert "Resumed agent session" in resumed
