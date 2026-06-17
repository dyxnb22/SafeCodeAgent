"""Cross-session memory isolation and injection tests.

Covers:
- Approved facts enter agent context; rejected/pending facts do not.
- Different project roots (.sac dirs) do not share facts or sessions.
- Pinned files are preserved across sessions.
- Secrets in session observations are not written to facts or summaries.
- Project notes are injected into agent context (regression for v6.6.x fix).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.memory.facts import ProjectFactStore
from safecode.memory.facade import MemoryFacade
from safecode.memory.session_store import SessionSummaryStore
from safecode.memory.summary import build_session_summary, format_memory_context


# ---------------------------------------------------------------------------
# Approved vs rejected/pending facts in context
# ---------------------------------------------------------------------------


class TestFactContextInjection:
    def test_approved_fact_appears_in_context(self, tmp_path: Path) -> None:
        sac_dir = tmp_path / ".sac"
        store = ProjectFactStore(sac_dir)
        fact = store.propose("test_command", "pytest -q", source="user")
        assert fact is not None
        store.approve(fact.fact_id)

        ctx = store.approved_context()
        assert "pytest -q" in ctx
        assert "test_command" in ctx

    def test_pending_fact_excluded_from_context(self, tmp_path: Path) -> None:
        sac_dir = tmp_path / ".sac"
        store = ProjectFactStore(sac_dir)
        store.propose("convention", "use snake_case everywhere", source="auto")

        ctx = store.approved_context()
        assert ctx == ""

    def test_rejected_fact_excluded_from_context(self, tmp_path: Path) -> None:
        sac_dir = tmp_path / ".sac"
        store = ProjectFactStore(sac_dir)
        fact = store.propose("test_command", "npm test", source="auto")
        assert fact is not None
        store.reject(fact.fact_id)

        ctx = store.approved_context()
        assert ctx == ""

    def test_mixed_statuses_only_approved_enter_context(self, tmp_path: Path) -> None:
        sac_dir = tmp_path / ".sac"
        store = ProjectFactStore(sac_dir)

        approved = store.propose("test_command", "pytest -q", source="user")
        assert approved is not None
        store.approve(approved.fact_id)

        pending = store.propose("lint_command", "ruff check .", source="auto")
        assert pending is not None  # pending, not approved

        rejected = store.propose("build_command", "make all", source="auto")
        assert rejected is not None
        store.reject(rejected.fact_id)

        ctx = store.approved_context()
        assert "pytest -q" in ctx
        assert "ruff check" not in ctx
        assert "make all" not in ctx


# ---------------------------------------------------------------------------
# Project isolation: different roots use different .sac dirs
# ---------------------------------------------------------------------------


class TestProjectIsolation:
    def test_facts_do_not_bleed_between_projects(self, tmp_path: Path) -> None:
        proj_a = tmp_path / "proj_a"
        proj_b = tmp_path / "proj_b"
        proj_a.mkdir()
        proj_b.mkdir()

        store_a = ProjectFactStore(proj_a / ".sac")
        store_b = ProjectFactStore(proj_b / ".sac")

        fact = store_a.propose("test_command", "pytest -q", source="user")
        assert fact is not None
        store_a.approve(fact.fact_id)

        # proj_b has no facts
        assert store_b.approved_context() == ""
        assert store_b.list_facts() == []

    def test_sessions_do_not_bleed_between_projects(self, tmp_path: Path) -> None:
        proj_a = tmp_path / "proj_a"
        proj_b = tmp_path / "proj_b"
        proj_a.mkdir()
        proj_b.mkdir()

        summary = build_session_summary(
            session_id="sess-001",
            goal="add feature X",
            step_observations=["edited src/main.py"],
            stopped_reason="completed",
            started_at="2026-06-17T10:00:00+00:00",
        )
        SessionSummaryStore(proj_a / ".sac").append(summary)

        # proj_b session store is empty
        assert SessionSummaryStore(proj_b / ".sac").load_recent() == []

    def test_pinned_files_isolated_per_project(self, tmp_path: Path) -> None:
        proj_a = tmp_path / "proj_a"
        proj_b = tmp_path / "proj_b"
        proj_a.mkdir()
        proj_b.mkdir()
        (proj_a / "src").mkdir()
        (proj_a / "src" / "main.py").write_text("")

        mem_a = MemoryFacade(proj_a)
        mem_b = MemoryFacade(proj_b)

        mem_a.pin_file("src/main.py")
        assert mem_b.read_pinned_files() == []


# ---------------------------------------------------------------------------
# Pinned files persistence
# ---------------------------------------------------------------------------


class TestPinnedFilePersistence:
    def test_pinned_files_survive_across_reads(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("")

        mem = MemoryFacade(tmp_path)
        mem.pin_file("src/app.py")

        # Re-read from disk
        mem2 = MemoryFacade(tmp_path)
        assert "src/app.py" in mem2.read_pinned_files()

    def test_unpin_removes_only_target(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")

        mem = MemoryFacade(tmp_path)
        mem.pin_file("a.py")
        mem.pin_file("b.py")
        mem.unpin_file("a.py")

        pins = mem.read_pinned_files()
        assert "b.py" in pins
        assert "a.py" not in pins


# ---------------------------------------------------------------------------
# Secrets not written to facts or session summaries
# ---------------------------------------------------------------------------


class TestSecretSafety:
    def test_sensitive_key_fact_not_stored(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        result = store.propose("api_key", "sk-abc123secret", source="auto")
        assert result is None
        assert store.list_facts() == []

    def test_sensitive_value_fact_not_stored(self, tmp_path: Path) -> None:
        store = ProjectFactStore(tmp_path / ".sac")
        result = store.propose("convention", "use token=mytoken for auth", source="auto")
        # _looks_sensitive checks value — "token" is in _SENSITIVE_WORDS
        assert result is None

    def test_session_summary_redacts_secrets_in_observations(self, tmp_path: Path) -> None:
        obs = ["edited config.py, set token=supersecretvalue123"]
        summary = build_session_summary(
            session_id="sess-secret",
            goal="configure auth",
            step_observations=obs,
            stopped_reason="completed",
            started_at="2026-06-17T10:00:00+00:00",
        )
        ctx = summary.to_context_block()
        assert "supersecretvalue123" not in ctx

    def test_project_note_refuses_sensitive_text(self, tmp_path: Path) -> None:
        mem = MemoryFacade(tmp_path)
        with pytest.raises(ValueError, match="sensitive"):
            mem.add_note("set api_key=sk-secret-value")


# ---------------------------------------------------------------------------
# Project notes injected into context (regression)
# ---------------------------------------------------------------------------


class TestProjectNotesInjection:
    def test_project_notes_readable_from_facade(self, tmp_path: Path) -> None:
        mem = MemoryFacade(tmp_path)
        mem.add_note("always run: pytest -q before committing")

        notes = mem.read_project_notes()
        assert "pytest -q" in notes

    def test_project_notes_prepended_via_loop_helper(self, tmp_path: Path) -> None:
        """AgentLoop._prepend_session_memory injects project notes into the goal string."""
        from unittest.mock import patch, MagicMock

        mem = MemoryFacade(tmp_path)
        mem.add_note("project convention: use type hints everywhere")

        # Construct a minimal AgentLoop pointed at tmp_path
        from safecode.agent.loop import AgentLoop
        loop = AgentLoop.__new__(AgentLoop)
        loop.project_root = tmp_path
        loop._sac_dir = tmp_path / ".sac"

        result = loop._prepend_session_memory("fix the bug")
        assert result is not None
        assert "type hints" in result
        assert "fix the bug" in result
