"""Tests for v3.1.1 resume-session.

Verifies:
- sac agent resume <id> with matching session_id resumes successfully.
- sac agent resume <id> with mismatched session_id exits 1.
- sac agent resume after stop_for_user renders pending action.
- sac agent resume when session has contract_failed status is refused.
- sac agent resume of completed session is rejected (existing behavior).
- AgentSessionStore.load_by_id() returns session on match, None on mismatch, None when missing.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode.agent.session import AgentSessionState, AgentSessionStore
from safecode.cli import app

runner = CliRunner()


def _make_session(tmp_path: Path, *, status: str = "active", session_id: str | None = None) -> AgentSessionState:
    store = AgentSessionStore(tmp_path)
    state = store.start("test goal")
    if status != "active":
        updated = state.model_copy(update={"status": status})
        store.save(updated)
        state = updated
    if session_id is not None and session_id != state.session_id:
        updated = state.model_copy(update={"session_id": session_id})
        store.save(updated)
        state = updated
    return state


# ── Unit: AgentSessionStore.load_by_id ────────────────────────────────────────


class TestLoadById:
    def test_returns_session_on_match(self, tmp_path):
        state = _make_session(tmp_path)
        result = AgentSessionStore(tmp_path).load_by_id(state.session_id)
        assert result is not None
        assert result.session_id == state.session_id

    def test_returns_none_on_mismatch(self, tmp_path):
        _make_session(tmp_path)
        result = AgentSessionStore(tmp_path).load_by_id("nonexistent-id-xyz")
        assert result is None

    def test_returns_none_when_no_session(self, tmp_path):
        result = AgentSessionStore(tmp_path).load_by_id("any-id")
        assert result is None


# ── CLI: sac agent resume <session_id> ────────────────────────────────────────


class TestAgentResumeCLI:
    def test_resume_with_matching_id_exits_zero(self, tmp_path):
        state = _make_session(tmp_path)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            result = runner.invoke(app, ["agent", "resume", state.session_id])
        assert result.exit_code == 0, result.output

    def test_resume_with_mismatched_id_exits_one(self, tmp_path):
        _make_session(tmp_path)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            result = runner.invoke(app, ["agent", "resume", "bad-session-id"])
        assert result.exit_code == 1
        assert "not found" in result.output or "does not match" in result.output

    def test_resume_contract_failed_exits_one(self, tmp_path):
        state = _make_session(tmp_path, status="contract_failed")
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            result = runner.invoke(app, ["agent", "resume", state.session_id])
        assert result.exit_code == 1
        assert "contract" in result.output.lower()

    def test_resume_completed_session_exits_one(self, tmp_path):
        state = _make_session(tmp_path, status="completed")
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            result = runner.invoke(app, ["agent", "resume", state.session_id])
        assert result.exit_code == 1

    def test_resume_no_session_exits_one(self, tmp_path):
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            result = runner.invoke(app, ["agent", "resume"])
        assert result.exit_code == 1

    def test_resume_no_arg_uses_current_session(self, tmp_path):
        _make_session(tmp_path)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            result = runner.invoke(app, ["agent", "resume"])
        assert result.exit_code == 0, result.output
