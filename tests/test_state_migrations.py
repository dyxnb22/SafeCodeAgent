"""Tests for the v2.3.7 state schema migration layer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safecode.state.migrations import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    SchemaVersionError,
    migrate_record,
)


# ── migrate_record() core behaviour ──────────────────────────────────────────


class TestMigrateRecord:
    def test_missing_schema_version_defaults_to_v1(self):
        result = migrate_record({"foo": "bar"})
        assert result["schema_version"] == 1

    def test_schema_version_1_passes_through(self):
        result = migrate_record({"schema_version": 1, "foo": "bar"})
        assert result["schema_version"] == 1
        assert result["foo"] == "bar"

    def test_underscore_prefix_variant_accepted(self):
        result = migrate_record({"_schema_version": 1, "foo": "bar"})
        assert result["schema_version"] == 1

    def test_canonical_key_preferred_over_underscore_variant(self):
        # If both keys are present, schema_version takes precedence.
        result = migrate_record({"schema_version": 1, "_schema_version": 99})
        assert result["schema_version"] == 1

    def test_future_version_raises_schema_version_error(self):
        with pytest.raises(SchemaVersionError, match="unsupported schema_version=999"):
            migrate_record({"schema_version": 999})

    def test_schema_version_error_is_value_error_subclass(self):
        with pytest.raises(ValueError):
            migrate_record({"schema_version": 42})

    def test_non_int_schema_version_treated_as_v1(self):
        result = migrate_record({"schema_version": "banana"})
        assert result["schema_version"] == 1

    def test_none_schema_version_treated_as_v1(self):
        result = migrate_record({"schema_version": None})
        assert result["schema_version"] == 1

    def test_negative_schema_version_normalised_to_v1(self):
        result = migrate_record({"schema_version": -5})
        assert result["schema_version"] == 1

    def test_original_dict_not_mutated(self):
        original = {"foo": "bar"}
        migrate_record(original)
        assert "schema_version" not in original

    def test_record_type_name_appears_in_error(self):
        with pytest.raises(SchemaVersionError, match="MyRecord"):
            migrate_record({"schema_version": 99}, record_type="MyRecord")

    def test_current_version_constant_is_supported(self):
        assert CURRENT_SCHEMA_VERSION in SUPPORTED_SCHEMA_VERSIONS

    def test_supported_versions_is_non_empty_frozenset(self):
        assert isinstance(SUPPORTED_SCHEMA_VERSIONS, frozenset)
        assert len(SUPPORTED_SCHEMA_VERSIONS) >= 1


# ── AgentSessionState migration ───────────────────────────────────────────────


class TestAgentSessionMigration:
    def test_old_session_without_schema_version_loads(self, tmp_path):
        """A session.json written before v2.3.7 (no schema_version) loads as v1."""
        from safecode.agent.session import AgentSessionStore
        from safecode.utils.time import utc_now_iso

        sac = tmp_path / ".sac"
        sac.mkdir()
        old_record = {
            "session_id": "abcd1234",
            "goal": "fix bug",
            "plan": [],
            "current_step": 0,
            "pending_action": None,
            "last_observation": "",
            "status": "active",
            "last_error": None,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            # no schema_version field
        }
        (sac / "session.json").write_text(json.dumps(old_record), encoding="utf-8")

        store = AgentSessionStore(tmp_path)
        state = store.load()
        assert state is not None
        assert state.session_id == "abcd1234"
        assert state.schema_version == 1

    def test_session_with_schema_version_1_loads(self, tmp_path):
        from safecode.agent.session import AgentSessionStore
        from safecode.utils.time import utc_now_iso

        sac = tmp_path / ".sac"
        sac.mkdir()
        record = {
            "session_id": "ef012345",
            "goal": "fix bug",
            "plan": [],
            "current_step": 0,
            "pending_action": None,
            "last_observation": "",
            "status": "active",
            "last_error": None,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "schema_version": 1,
        }
        (sac / "session.json").write_text(json.dumps(record), encoding="utf-8")

        store = AgentSessionStore(tmp_path)
        state = store.load()
        assert state is not None
        assert state.schema_version == 1

    def test_session_with_future_version_returns_none(self, tmp_path):
        """Fail closed: unsupported schema_version causes load() to return None."""
        from safecode.agent.session import AgentSessionStore
        from safecode.utils.time import utc_now_iso

        sac = tmp_path / ".sac"
        sac.mkdir()
        future_record = {
            "session_id": "future01",
            "goal": "future goal",
            "plan": [],
            "current_step": 0,
            "pending_action": None,
            "last_observation": "",
            "status": "active",
            "last_error": None,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "schema_version": 9999,
        }
        (sac / "session.json").write_text(json.dumps(future_record), encoding="utf-8")

        store = AgentSessionStore(tmp_path)
        assert store.load() is None

    def test_new_session_is_saved_with_schema_version(self, tmp_path):
        from safecode.agent.session import AgentSessionStore

        store = AgentSessionStore(tmp_path)
        store.start("test goal")
        data = json.loads((tmp_path / ".sac" / "session.json").read_text(encoding="utf-8"))
        assert "schema_version" in data
        assert data["schema_version"] == 1


# ── AgentJournalEvent migration ───────────────────────────────────────────────


class TestAgentJournalMigration:
    def _write_journal(self, path: Path, events: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
        )

    def test_old_events_without_schema_version_load(self, tmp_path):
        from safecode.state.journal import AgentJournalStore

        journal_dir = tmp_path / ".sac" / "agent_journals"
        sid = "sessionabc"
        old_event = {
            "event_id": "ev001",
            "session_id": sid,
            "type": "plan",
            "message": "planned",
            "timestamp": "2025-01-01T00:00:00Z",
            "step": None,
            "payload": {},
            # no schema_version
        }
        self._write_journal(journal_dir / f"{sid}.jsonl", [old_event])

        store = AgentJournalStore(tmp_path)
        events = store.read(sid)
        assert len(events) == 1
        assert events[0].type == "plan"
        assert events[0].schema_version == 1

    def test_future_schema_version_event_is_skipped(self, tmp_path):
        """Journal events with unsupported schema_version are silently skipped."""
        from safecode.state.journal import AgentJournalStore

        journal_dir = tmp_path / ".sac" / "agent_journals"
        sid = "sessiondef"
        good_event = {
            "event_id": "ev001",
            "session_id": sid,
            "type": "plan",
            "message": "planned",
            "timestamp": "2025-01-01T00:00:00Z",
            "step": None,
            "payload": {},
            "schema_version": 1,
        }
        bad_event = {
            "event_id": "ev002",
            "session_id": sid,
            "type": "action",
            "message": "future event",
            "timestamp": "2025-01-01T00:00:01Z",
            "step": 1,
            "payload": {},
            "schema_version": 9999,
        }
        self._write_journal(journal_dir / f"{sid}.jsonl", [good_event, bad_event])

        store = AgentJournalStore(tmp_path)
        events = store.read(sid)
        # The future event is skipped; good event remains.
        assert len(events) == 1
        assert events[0].event_id == "ev001"

    def test_new_events_are_saved_with_schema_version(self, tmp_path):
        from safecode.agent.session import AgentSessionStore
        from safecode.state.journal import AgentJournalStore

        state = AgentSessionStore(tmp_path).start("schema test")
        events = AgentJournalStore(tmp_path).read(state.session_id)
        assert events, "expected at least one event (plan)"
        assert all(e.schema_version == 1 for e in events)


# ── MCPWriteProposal migration ────────────────────────────────────────────────


class TestMCPProposalMigration:
    def test_old_proposal_without_schema_version_loads(self, tmp_path):
        """Proposals written before v2.3.7 (no schema_version) load as v1."""
        from safecode.mcp.proposal import MCPWriteProposalStore

        sac = tmp_path / ".sac"
        sac.mkdir()
        old_proposal = {
            "proposal_id": "prop-001",
            "server": "notion",
            "tool": "create",
            "classification": "write",
            "input_payload": {},
            "input_hash": "abc123",
            "created_at": "2025-01-01T00:00:00Z",
            "status": "pending",
            "risk_level": "high",
            "reason": "test",
            # no schema_version
        }
        (sac / "pending_mcp_call.json").write_text(
            json.dumps(old_proposal), encoding="utf-8"
        )

        store = MCPWriteProposalStore(tmp_path)
        proposal = store.load_pending()
        assert proposal is not None
        assert proposal.proposal_id == "prop-001"
        assert proposal.schema_version == 1

    def test_proposal_with_schema_version_1_loads(self, tmp_path):
        from safecode.mcp.proposal import MCPWriteProposalStore

        sac = tmp_path / ".sac"
        sac.mkdir()
        record = {
            "proposal_id": "prop-002",
            "server": "notion",
            "tool": "update",
            "classification": "write",
            "input_payload": {},
            "input_hash": "def456",
            "created_at": "2025-01-01T00:00:00Z",
            "status": "pending",
            "risk_level": "high",
            "reason": "test",
            "schema_version": 1,
        }
        (sac / "pending_mcp_call.json").write_text(json.dumps(record), encoding="utf-8")

        store = MCPWriteProposalStore(tmp_path)
        proposal = store.load_pending()
        assert proposal is not None
        assert proposal.schema_version == 1

    def test_proposal_with_future_version_returns_none(self, tmp_path):
        from safecode.mcp.proposal import MCPWriteProposalStore

        sac = tmp_path / ".sac"
        sac.mkdir()
        future_record = {
            "proposal_id": "prop-999",
            "server": "notion",
            "tool": "delete",
            "classification": "write",
            "input_payload": {},
            "input_hash": "xyz789",
            "created_at": "2025-01-01T00:00:00Z",
            "status": "pending",
            "risk_level": "critical",
            "reason": "test",
            "schema_version": 9999,
        }
        (sac / "pending_mcp_call.json").write_text(
            json.dumps(future_record), encoding="utf-8"
        )

        store = MCPWriteProposalStore(tmp_path)
        assert store.load_pending() is None
