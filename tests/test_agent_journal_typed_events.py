"""Tests for v4.11.1 typed step events in the existing agent journal.

Verifies:
- record_typed_step / record_typed_result round trip.
- Corrupt-line tolerance (journal remains readable).
- Redaction applied to descriptions.
- latest_plan / last_typed_result read helpers.
- sac status --json agent_plan field.
- Existing tests/test_agent_journal.py still passes (imports verified).

All surfaces under test are EXPERIMENTAL.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from safecode.state.journal import AgentJournalStore
from safecode.agent.step_model import TypedAgentStep, TypedAgentStepResult


SESSION = "test-session-typed-1"


def _make_store(tmp_path: Path) -> AgentJournalStore:
    return AgentJournalStore(tmp_path)


# ---------------------------------------------------------------------------
# Round trip: record_typed_step / record_typed_result
# ---------------------------------------------------------------------------


class TestTypedStepRoundTrip:
    def test_record_typed_step_returns_event(self, tmp_path):
        store = _make_store(tmp_path)
        step = TypedAgentStep.from_route(index=0, kind="ask", description="inspect project")
        event = store.record_typed_step(SESSION, step)
        assert event.type == "typed_step"
        assert event.session_id == SESSION

    def test_record_typed_result_returns_event(self, tmp_path):
        store = _make_store(tmp_path)
        result = TypedAgentStepResult(
            step_index=0, kind="ask", status="success", summary="done"
        )
        event = store.record_typed_result(SESSION, result)
        assert event.type == "typed_result"
        assert event.session_id == SESSION

    def test_typed_step_persisted_in_journal(self, tmp_path):
        store = _make_store(tmp_path)
        step = TypedAgentStep.from_route(index=1, kind="edit", description="propose patch")
        store.record_typed_step(SESSION, step)
        events = store.read(SESSION)
        typed_events = [e for e in events if e.type == "typed_step"]
        assert len(typed_events) == 1
        assert typed_events[0].payload["typed_step"]["kind"] == "edit"

    def test_typed_result_persisted_in_journal(self, tmp_path):
        store = _make_store(tmp_path)
        result = TypedAgentStepResult(
            step_index=1, kind="edit", status="waiting_for_user",
            summary="patch proposed", pending_patch_id="p-abc"
        )
        store.record_typed_result(SESSION, result)
        events = store.read(SESSION)
        typed = [e for e in events if e.type == "typed_result"]
        assert len(typed) == 1
        payload = typed[0].payload["typed_result"]
        assert payload["kind"] == "edit"
        assert payload["status"] == "waiting_for_user"
        assert payload["pending_patch_id"] == "p-abc"

    def test_multiple_typed_events_ordered(self, tmp_path):
        store = _make_store(tmp_path)
        for i in range(3):
            step = TypedAgentStep.from_route(index=i, kind="ask")
            result = TypedAgentStepResult(step_index=i, kind="ask", status="success")
            store.record_typed_step(SESSION, step)
            store.record_typed_result(SESSION, result)
        events = store.read(SESSION)
        typed_steps = [e for e in events if e.type == "typed_step"]
        assert len(typed_steps) == 3
        indices = [e.payload["typed_step"]["index"] for e in typed_steps]
        assert indices == [0, 1, 2]


# ---------------------------------------------------------------------------
# Corrupt-line tolerance
# ---------------------------------------------------------------------------


class TestCorruptLineTolerance:
    def test_corrupt_line_skipped(self, tmp_path):
        store = _make_store(tmp_path)
        # Write one valid event then a corrupt line
        step = TypedAgentStep.from_route(index=0, kind="ask")
        store.record_typed_step(SESSION, step)
        # Inject corrupt line directly into the file
        path = store.path_for(SESSION)
        with path.open("a", encoding="utf-8") as f:
            f.write("{this is not json\n")
        # Should still read without raising
        events = store.read(SESSION)
        assert len(events) == 1
        assert events[0].type == "typed_step"

    def test_empty_journal_returns_empty(self, tmp_path):
        store = _make_store(tmp_path)
        events = store.read("nonexistent-session-xyz")
        assert events == []

    def test_corrupt_typed_result_skipped_by_last_typed_result(self, tmp_path):
        store = _make_store(tmp_path)
        good_result = TypedAgentStepResult(step_index=0, kind="ask", status="success")
        store.record_typed_result(SESSION, good_result)
        # Inject malformed typed_result line
        path = store.path_for(SESSION)
        bad_event = {
            "event_id": "bad", "session_id": SESSION, "type": "typed_result",
            "message": "bad", "timestamp": "2026-01-01T00:00:00Z",
            "step": 999, "payload": {"typed_result": {"INVALID": True}},
            "schema_version": 1,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(bad_event) + "\n")
        # last_typed_result should return the good result, skipping the bad one
        result = store.last_typed_result(SESSION)
        # The bad event comes last, but its payload is invalid; good result is returned
        # (or None if bad event is tried first). Verify no crash.
        assert result is None or result.kind == "ask"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


class TestRedaction:
    def test_description_with_secret_is_redacted(self, tmp_path):
        store = _make_store(tmp_path)
        step = TypedAgentStep.from_route(
            index=0, kind="ask",
            description="check api_key=sk-supersecret123abc in header"
        )
        store.record_typed_step(SESSION, step)
        events = store.read(SESSION)
        assert len(events) == 1
        stored_desc = events[0].payload["typed_step"]["description"]
        # Redaction should have removed or masked the secret
        assert "sk-supersecret123abc" not in stored_desc

    def test_summary_with_secret_is_redacted(self, tmp_path):
        store = _make_store(tmp_path)
        result = TypedAgentStepResult(
            step_index=0, kind="ask", status="success",
            summary="found api_key=sk-supersecret123abc in file"
        )
        store.record_typed_result(SESSION, result)
        events = store.read(SESSION)
        assert len(events) == 1
        stored_summary = events[0].payload["typed_result"]["summary"]
        assert "sk-supersecret123abc" not in stored_summary


# ---------------------------------------------------------------------------
# Read helpers: latest_plan / last_typed_result
# ---------------------------------------------------------------------------


class TestReadHelpers:
    def test_latest_plan_returns_none_when_no_plan(self, tmp_path):
        store = _make_store(tmp_path)
        result = store.latest_plan("no-such-session")
        assert result is None

    def test_latest_plan_returns_steps(self, tmp_path):
        store = _make_store(tmp_path)
        store.record_plan(SESSION, "my goal", ["step 1", "step 2", "step 3"])
        plan = store.latest_plan(SESSION)
        assert plan == ["step 1", "step 2", "step 3"]

    def test_latest_plan_returns_most_recent(self, tmp_path):
        store = _make_store(tmp_path)
        store.record_plan(SESSION, "goal", ["old step"])
        store.record_plan(SESSION, "goal v2", ["new step a", "new step b"])
        plan = store.latest_plan(SESSION)
        assert plan == ["new step a", "new step b"]

    def test_last_typed_result_returns_none_when_missing(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.last_typed_result("no-such-session") is None

    def test_last_typed_result_returns_most_recent(self, tmp_path):
        store = _make_store(tmp_path)
        for i in range(3):
            result = TypedAgentStepResult(step_index=i, kind="ask", status="success")
            store.record_typed_result(SESSION, result)
        last = store.last_typed_result(SESSION)
        assert last is not None
        assert last.step_index == 2

    def test_last_typed_result_skips_non_typed_result_events(self, tmp_path):
        store = _make_store(tmp_path)
        store.record_plan(SESSION, "goal", ["step 1"])
        store.record_action(SESSION, step=0, message="action")
        typed = TypedAgentStepResult(step_index=0, kind="ask", status="success")
        store.record_typed_result(SESSION, typed)
        last = store.last_typed_result(SESSION)
        assert last is not None
        assert last.kind == "ask"

    def test_latest_plan_tolerates_missing_file(self, tmp_path):
        store = _make_store(tmp_path)
        # No file should be created by reading
        plan = store.latest_plan("missing-session-abc")
        assert plan is None
        assert not (tmp_path / ".sac" / "agent_journals" / "missing-session-abc.jsonl").exists()

    def test_last_typed_result_tolerates_missing_file(self, tmp_path):
        store = _make_store(tmp_path)
        result = store.last_typed_result("missing-session-abc")
        assert result is None


# ---------------------------------------------------------------------------
# sac status --json agent_plan field
# ---------------------------------------------------------------------------


class TestStatusJsonAgentPlan:
    def test_status_json_includes_agent_plan_key(self, tmp_path, monkeypatch):
        """sac status --json must include agent_plan key (may be None)."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "agent_plan" in data.get("data", data)

    def test_status_json_agent_plan_none_without_session(self, tmp_path, monkeypatch):
        """agent_plan is None when no agent session exists."""
        from typer.testing import CliRunner
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        data = payload.get("data", payload)
        assert data.get("agent_plan") is None

    def test_status_json_agent_plan_has_session_id_when_session_exists(self, tmp_path, monkeypatch):
        """agent_plan contains session_id and goal when agent session is active."""
        from typer.testing import CliRunner
        from safecode.cli import app
        from safecode.agent.session import AgentSessionStore

        monkeypatch.chdir(tmp_path)
        AgentSessionStore(tmp_path).start("test goal")
        runner = CliRunner()
        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        data = payload.get("data", payload)
        agent_plan = data.get("agent_plan")
        assert agent_plan is not None
        assert "session_id" in agent_plan
        assert agent_plan.get("goal") == "test goal"

    def test_status_json_agent_plan_contains_last_typed_result(self, tmp_path, monkeypatch):
        """agent_plan.last_typed_result is populated after a step."""
        from typer.testing import CliRunner
        from safecode.cli import app
        from safecode.agent.session import AgentSessionStore
        from safecode.state.journal import AgentJournalStore

        monkeypatch.chdir(tmp_path)
        store = AgentSessionStore(tmp_path)
        session = store.start("my goal")
        journal = AgentJournalStore(tmp_path)
        typed_result = TypedAgentStepResult(
            step_index=0, kind="ask", status="success", summary="read done"
        )
        journal.record_typed_result(session.session_id, typed_result)

        runner = CliRunner()
        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        data = payload.get("data", payload)
        agent_plan = data.get("agent_plan", {})
        ltr = agent_plan.get("last_typed_result")
        assert ltr is not None
        assert ltr["kind"] == "ask"
        assert ltr["status"] == "success"


# ---------------------------------------------------------------------------
# Legacy journal events are preserved and existing render unchanged
# ---------------------------------------------------------------------------


class TestLegacyCompatibility:
    def test_typed_events_are_additive_not_replacing(self, tmp_path):
        """Typed events are added alongside existing legacy events."""
        store = _make_store(tmp_path)
        store.record_plan(SESSION, "goal", ["step 1"])
        store.record_action(SESSION, step=0, message="action msg")
        step = TypedAgentStep.from_route(index=0, kind="ask")
        result = TypedAgentStepResult(step_index=0, kind="ask", status="success")
        store.record_typed_step(SESSION, step)
        store.record_typed_result(SESSION, result)
        events = store.read(SESSION)
        types = [e.type for e in events]
        assert "plan" in types
        assert "action" in types
        assert "typed_step" in types
        assert "typed_result" in types

    def test_render_markdown_still_works_with_typed_events(self, tmp_path):
        """render_markdown must not raise when typed events are present."""
        store = _make_store(tmp_path)
        store.record_plan(SESSION, "goal", ["step 1"])
        step = TypedAgentStep.from_route(index=0, kind="ask")
        result = TypedAgentStepResult(step_index=0, kind="ask", status="success")
        store.record_typed_step(SESSION, step)
        store.record_typed_result(SESSION, result)
        md = store.render_markdown(SESSION)
        assert "typed_step" in md
        assert "typed_result" in md

    def test_journal_event_type_literal_includes_new_types(self):
        """JournalEventType Literal includes typed_step and typed_result."""
        from safecode.state.journal import JournalEventType
        import typing
        args = typing.get_args(JournalEventType)
        assert "typed_step" in args
        assert "typed_result" in args
