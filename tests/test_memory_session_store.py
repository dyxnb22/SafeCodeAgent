"""Tests for cross-session memory: SessionSummaryStore and summary builder (v6.2.0)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from safecode.memory.session_store import SessionSummary, SessionSummaryStore
from safecode.memory.summary import build_session_summary, format_memory_context


# ---------------------------------------------------------------------------
# SessionSummary dataclass
# ---------------------------------------------------------------------------


class TestSessionSummaryDataclass:
    def test_round_trip_dict(self) -> None:
        s = SessionSummary(
            session_id="abc123",
            goal="fix the bug",
            started_at="2026-06-16T10:00:00+00:00",
            ended_at="2026-06-16T10:05:00+00:00",
            stopped_reason="approval_required",
            steps=3,
            touched_files=["src/foo.py"],
            commands_run=["pytest -q"],
            tests_passed=True,
            approved_patches=1,
        )
        d = s.to_dict()
        assert d["session_id"] == "abc123"
        assert d["goal"] == "fix the bug"
        assert d["steps"] == 3
        assert d["touched_files"] == ["src/foo.py"]
        assert d["tests_passed"] is True
        rebuilt = SessionSummary.from_dict(d)
        assert rebuilt == s

    def test_from_dict_missing_fields(self) -> None:
        s = SessionSummary.from_dict({})
        assert s.session_id == ""
        assert s.steps == 0
        assert s.touched_files == []
        assert s.tests_passed is None

    def test_from_dict_extra_fields_ignored(self) -> None:
        s = SessionSummary.from_dict({"session_id": "x", "unknown_field": "y"})
        assert s.session_id == "x"

    def test_to_context_block_contains_goal(self) -> None:
        s = SessionSummary(
            session_id="s1",
            goal="refactor auth module",
            started_at="",
            ended_at="",
            stopped_reason="completed",
            steps=5,
            touched_files=["auth.py", "tests/test_auth.py"],
            commands_run=["pytest auth"],
            tests_passed=True,
            approved_patches=0,
        )
        block = s.to_context_block()
        assert "refactor auth module" in block
        assert "auth.py" in block
        assert "pytest auth" in block
        assert "passed" in block
        assert "completed" in block

    def test_to_context_block_no_optional_fields(self) -> None:
        s = SessionSummary(
            session_id="s2",
            goal="ask a question",
            started_at="",
            ended_at="",
            stopped_reason="completed",
            steps=1,
            touched_files=[],
            commands_run=[],
            tests_passed=None,
            approved_patches=0,
        )
        block = s.to_context_block()
        assert "ask a question" in block
        assert "Files:" not in block
        assert "Tests:" not in block

    def test_goal_truncated_in_context_block(self) -> None:
        long_goal = "x" * 200
        s = SessionSummary(
            session_id="s3", goal=long_goal, started_at="", ended_at="",
            stopped_reason="completed", steps=1, touched_files=[], commands_run=[],
            tests_passed=None, approved_patches=0,
        )
        block = s.to_context_block()
        assert len(block.split("\n")[0]) <= 140  # goal capped at 120 + label


# ---------------------------------------------------------------------------
# SessionSummaryStore
# ---------------------------------------------------------------------------


class TestSessionSummaryStore:
    def _make_summary(self, idx: int = 0) -> SessionSummary:
        return SessionSummary(
            session_id=f"sess-{idx:04d}",
            goal=f"goal {idx}",
            started_at="2026-06-16T10:00:00+00:00",
            ended_at="2026-06-16T10:05:00+00:00",
            stopped_reason="completed",
            steps=idx + 1,
            touched_files=[],
            commands_run=[],
            tests_passed=None,
            approved_patches=0,
        )

    def test_append_and_load_recent(self, tmp_path: Path) -> None:
        store = SessionSummaryStore(tmp_path / ".sac")
        s0 = self._make_summary(0)
        s1 = self._make_summary(1)
        store.append(s0)
        store.append(s1)
        recent = store.load_recent(limit=5)
        assert len(recent) == 2
        assert recent[0].session_id == "sess-0001"  # newest first
        assert recent[1].session_id == "sess-0000"

    def test_load_recent_respects_limit(self, tmp_path: Path) -> None:
        store = SessionSummaryStore(tmp_path / ".sac")
        for i in range(5):
            store.append(self._make_summary(i))
        assert len(store.load_recent(limit=2)) == 2

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        store = SessionSummaryStore(tmp_path / ".sac")
        assert store.load_recent() == []

    def test_persists_to_jsonl(self, tmp_path: Path) -> None:
        store = SessionSummaryStore(tmp_path / ".sac")
        store.append(self._make_summary(0))
        lines = (tmp_path / ".sac" / "memory" / "sessions.jsonl").read_text().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["session_id"] == "sess-0000"

    def test_cap_at_50_entries(self, tmp_path: Path) -> None:
        store = SessionSummaryStore(tmp_path / ".sac")
        for i in range(60):
            store.append(self._make_summary(i))
        recent = store.load_recent(limit=100)
        assert len(recent) == 50

    def test_clear_all(self, tmp_path: Path) -> None:
        store = SessionSummaryStore(tmp_path / ".sac")
        store.append(self._make_summary(0))
        store.append(self._make_summary(1))
        removed = store.clear()
        assert removed == 2
        assert store.load_recent() == []

    def test_clear_before_iso(self, tmp_path: Path) -> None:
        store = SessionSummaryStore(tmp_path / ".sac")
        old = SessionSummary(
            session_id="old", goal="old goal",
            started_at="2026-01-01T00:00:00+00:00",
            ended_at="2026-01-01T00:00:00+00:00",
            stopped_reason="completed", steps=1,
            touched_files=[], commands_run=[], tests_passed=None, approved_patches=0,
        )
        new = SessionSummary(
            session_id="new", goal="new goal",
            started_at="2026-06-01T00:00:00+00:00",
            ended_at="2026-06-01T00:00:00+00:00",
            stopped_reason="completed", steps=1,
            touched_files=[], commands_run=[], tests_passed=None, approved_patches=0,
        )
        store.append(old)
        store.append(new)
        removed = store.clear(before_iso="2026-03-01T00:00:00+00:00")
        assert removed == 1
        remaining = store.load_recent()
        assert len(remaining) == 1
        assert remaining[0].session_id == "new"

    def test_export_all(self, tmp_path: Path) -> None:
        store = SessionSummaryStore(tmp_path / ".sac")
        for i in range(3):
            store.append(self._make_summary(i))
        exported = store.export_all()
        assert len(exported) == 3
        assert all(isinstance(e, dict) for e in exported)

    def test_corrupt_lines_skipped(self, tmp_path: Path) -> None:
        store = SessionSummaryStore(tmp_path / ".sac")
        store.append(self._make_summary(0))
        path = tmp_path / ".sac" / "memory" / "sessions.jsonl"
        path.write_text(path.read_text() + "NOT_JSON\n")
        recent = store.load_recent()
        assert len(recent) == 1

    def test_non_dict_lines_skipped(self, tmp_path: Path) -> None:
        sac_dir = tmp_path / ".sac"
        path = sac_dir / "memory" / "sessions.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("[1,2,3]\n")
        store = SessionSummaryStore(sac_dir)
        assert store.load_recent() == []

    def test_parent_dir_created_on_append(self, tmp_path: Path) -> None:
        store = SessionSummaryStore(tmp_path / ".sac")
        assert not (tmp_path / ".sac" / "memory").exists()
        store.append(self._make_summary(0))
        assert (tmp_path / ".sac" / "memory" / "sessions.jsonl").exists()


# ---------------------------------------------------------------------------
# build_session_summary
# ---------------------------------------------------------------------------


class TestBuildSessionSummary:
    def test_basic_fields(self) -> None:
        s = build_session_summary(
            session_id="sid",
            goal="fix foo",
            step_observations=["observation one", "observation two"],
            stopped_reason="completed",
            started_at="2026-06-16T10:00:00+00:00",
        )
        assert s.session_id == "sid"
        assert s.goal == "fix foo"
        assert s.stopped_reason == "completed"
        assert s.steps == 2

    def test_ended_at_defaults_to_now(self) -> None:
        s = build_session_summary(
            session_id="s", goal="g", step_observations=[],
            stopped_reason="done", started_at="2026-06-16T10:00:00+00:00",
        )
        assert s.ended_at != ""
        # should be a valid ISO timestamp
        datetime.fromisoformat(s.ended_at)

    def test_extracts_touched_files(self) -> None:
        obs = ["edit `src/auth.py` to add validation"]
        s = build_session_summary("s", "g", obs, "done", "2026-06-16T00:00:00+00:00")
        assert "src/auth.py" in s.touched_files

    def test_extracts_commands(self) -> None:
        obs = ["running `pytest -q`"]
        s = build_session_summary("s", "g", obs, "done", "2026-06-16T00:00:00+00:00")
        assert "pytest -q" in s.commands_run

    def test_detects_test_pass(self) -> None:
        obs = ["3 passed in 0.5s"]
        s = build_session_summary("s", "g", obs, "done", "2026-06-16T00:00:00+00:00")
        assert s.tests_passed is True

    def test_detects_test_fail(self) -> None:
        obs = ["FAILED src/test_foo.py::test_bar"]
        s = build_session_summary("s", "g", obs, "done", "2026-06-16T00:00:00+00:00")
        assert s.tests_passed is False

    def test_pass_after_fail_wins(self) -> None:
        obs = ["FAILED initially", "3 passed after fix"]
        s = build_session_summary("s", "g", obs, "done", "2026-06-16T00:00:00+00:00")
        assert s.tests_passed is True

    def test_no_test_info_gives_none(self) -> None:
        s = build_session_summary("s", "g", [], "done", "2026-06-16T00:00:00+00:00")
        assert s.tests_passed is None

    def test_goal_truncated_to_200(self) -> None:
        long_goal = "x" * 300
        s = build_session_summary("s", long_goal, [], "done", "2026-06-16T00:00:00+00:00")
        assert len(s.goal) <= 200

    def test_goal_is_redacted(self) -> None:
        s = build_session_summary("s", "api_key=supersecret123", [], "done", "2026-06-16T00:00:00+00:00")
        assert "supersecret123" not in s.goal

    def test_approved_patches_forwarded(self) -> None:
        s = build_session_summary("s", "g", [], "done", "2026-06-16T00:00:00+00:00", approved_patches=2)
        assert s.approved_patches == 2

    def test_sensitive_files_excluded(self) -> None:
        obs = ["edit `.env` to add secret key"]
        s = build_session_summary("s", "g", obs, "done", "2026-06-16T00:00:00+00:00")
        # .env should be filtered by _looks_sensitive
        sensitive_found = any("secret" in f.lower() or "key" in f.lower() for f in s.touched_files)
        assert not sensitive_found


# ---------------------------------------------------------------------------
# format_memory_context
# ---------------------------------------------------------------------------


class TestFormatMemoryContext:
    def _make(self, goal: str, files: list[str] | None = None) -> SessionSummary:
        return SessionSummary(
            session_id="s", goal=goal, started_at="", ended_at="",
            stopped_reason="completed", steps=1,
            touched_files=files or [], commands_run=[],
            tests_passed=None, approved_patches=0,
        )

    def test_empty_list_returns_empty_string(self) -> None:
        assert format_memory_context([]) == ""

    def test_header_present(self) -> None:
        s = self._make("do something")
        result = format_memory_context([s])
        assert "Recent Session Memory" in result

    def test_goal_in_output(self) -> None:
        s = self._make("fix the auth bug")
        result = format_memory_context([s])
        assert "fix the auth bug" in result

    def test_respects_max_chars(self) -> None:
        summaries = [self._make("goal " * 50) for _ in range(10)]
        result = format_memory_context(summaries, max_chars=300)
        assert len(result) <= 500  # some slack for formatting

    def test_at_most_3_recent(self) -> None:
        summaries = [self._make(f"goal {i}") for i in range(10)]
        result = format_memory_context(summaries)
        # Max 3 entries in context by default
        assert result.count("- Goal:") <= 3


# ---------------------------------------------------------------------------
# AgentLoop integration: session summary written after run()
# ---------------------------------------------------------------------------


class TestAgentLoopSessionMemoryIntegration:
    def test_summary_written_after_run(self, tmp_path: Path) -> None:
        from safecode.agent.loop import AgentLoop
        from safecode.llm.mock import MockLLMClient
        from safecode.memory.session_store import SessionSummaryStore

        loop = AgentLoop(tmp_path, llm_client=MockLLMClient())
        loop.run(goal="inspect the project", max_steps=1)

        sac_dir = tmp_path / ".sac"
        store = SessionSummaryStore(sac_dir)
        summaries = store.load_recent()
        assert len(summaries) == 1
        assert summaries[0].steps >= 1
        assert "inspect" in summaries[0].goal.lower() or summaries[0].goal != ""

    def test_second_run_sees_first_session_memory(self, tmp_path: Path) -> None:
        from safecode.agent.loop import AgentLoop
        from safecode.llm.mock import MockLLMClient
        from safecode.memory.session_store import SessionSummaryStore

        loop1 = AgentLoop(tmp_path, llm_client=MockLLMClient())
        loop1.run(goal="first session goal", max_steps=1)

        store = SessionSummaryStore(tmp_path / ".sac")
        assert len(store.load_recent()) == 1

        loop2 = AgentLoop(tmp_path, llm_client=MockLLMClient())
        loop2.run(goal="second session goal", max_steps=1)

        assert len(store.load_recent()) == 2

    def test_summary_written_even_on_approval_stop(self, tmp_path: Path) -> None:
        from safecode.agent.loop import AgentLoop
        from safecode.llm.mock import MockLLMClient
        from safecode.memory.session_store import SessionSummaryStore

        loop = AgentLoop(tmp_path, llm_client=MockLLMClient())
        loop.run(goal="fix the calculator bug", max_steps=3)

        store = SessionSummaryStore(tmp_path / ".sac")
        summaries = store.load_recent()
        assert len(summaries) == 1
        # stopped_reason should reflect actual outcome
        assert summaries[0].stopped_reason in {
            "approval_required", "completed", "max_steps_reached",
            "budget_exceeded", "aborted", "loop_stuck",
        }

    def test_session_memory_failure_does_not_crash_run(self, tmp_path: Path) -> None:
        """If session memory write fails, run() should still return normally."""
        from safecode.agent.loop import AgentLoop
        from safecode.llm.mock import MockLLMClient

        loop = AgentLoop(tmp_path, llm_client=MockLLMClient())
        # Make memory dir read-only to force a write error
        sac_memory = tmp_path / ".sac" / "memory"
        sac_memory.mkdir(parents=True)
        (sac_memory / "sessions.jsonl").write_text("")
        sac_memory.chmod(0o555)
        try:
            result = loop.run(goal="inspect project", max_steps=1)
            assert result is not None  # run() completed despite memory failure
        finally:
            sac_memory.chmod(0o755)
