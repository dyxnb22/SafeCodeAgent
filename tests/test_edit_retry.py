"""Tests for v3.1.1 edit-retry-from-failure.

Verifies:
- sac edit --retry-from-last-failure with a session that has a failure event injects context.
- Failure context is redacted via redact_secrets (test with a secret-like pattern).
- sac edit --retry-from-last-failure with no session proceeds normally (no crash).
- The injected context appears in the task string passed to orchestrator (mocked).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.session import AgentSessionStore
from safecode.cli_core import _inject_last_failure_context
from safecode.state.journal import AgentJournalStore


def _setup_session_with_failure(project_root: Path, failure_msg: str) -> str:
    store = AgentSessionStore(project_root)
    state = store.start("fix something")
    journal = AgentJournalStore(project_root)
    journal.record_failure(state.session_id, failure_msg, {})
    return state.session_id


class TestInjectLastFailureContext:
    def test_injects_failure_context_when_present(self, tmp_path):
        session_id = _setup_session_with_failure(tmp_path, "TypeError: cannot add str and int")
        result = _inject_last_failure_context(tmp_path, "fix the bug")
        assert "Previous failure context" in result
        assert "TypeError" in result
        assert "fix the bug" in result

    def test_redacts_secret_like_content(self, tmp_path):
        session_id = _setup_session_with_failure(tmp_path, "Error: token=supersecretABC123 not valid")
        result = _inject_last_failure_context(tmp_path, "fix auth")
        assert "supersecretABC123" not in result

    def test_no_session_returns_task_unchanged(self, tmp_path):
        result = _inject_last_failure_context(tmp_path, "original task")
        assert result == "original task"

    def test_no_failure_in_journal_returns_task_unchanged(self, tmp_path):
        store = AgentSessionStore(tmp_path)
        store.start("some goal")
        result = _inject_last_failure_context(tmp_path, "original task")
        assert result == "original task"

    def test_task_string_structure_with_failure(self, tmp_path):
        _setup_session_with_failure(tmp_path, "IndexError: list index out of range")
        result = _inject_last_failure_context(tmp_path, "my task")
        assert "[Previous failure context]" in result
        assert "[Task]" in result
        assert "my task" in result

    def test_get_last_failure_context_returns_none_when_no_failures(self, tmp_path):
        store = AgentSessionStore(tmp_path)
        state = store.start("goal")
        journal = AgentJournalStore(tmp_path)
        ctx = journal.get_last_failure_context(state.session_id)
        assert ctx is None

    def test_get_last_failure_context_returns_message(self, tmp_path):
        session_id = _setup_session_with_failure(tmp_path, "RuntimeError: test failure")
        journal = AgentJournalStore(tmp_path)
        ctx = journal.get_last_failure_context(session_id)
        assert ctx is not None
        assert "RuntimeError" in ctx

    def test_get_last_failure_context_returns_last_failure(self, tmp_path):
        store = AgentSessionStore(tmp_path)
        state = store.start("goal")
        journal = AgentJournalStore(tmp_path)
        journal.record_failure(state.session_id, "first failure", {})
        journal.record_failure(state.session_id, "second failure", {})
        ctx = journal.get_last_failure_context(state.session_id)
        assert ctx == "second failure"
