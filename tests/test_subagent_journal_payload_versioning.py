"""Tests for subagent journal payload versioning (v2.9.6 + v2.9.7 adversarial).

Covers:
- SubagentDispatchPayload typed model: defaults, field coercion, extra fields ignored
- Old journals (no payload_version) parse with default version 1 — backward compat
- New journals include payload_version=1 via record_subagent_dispatch
- Unsupported future versions emit RuntimeWarning and are skipped (fail closed)
- Malformed payloads emit RuntimeWarning and are skipped (fail closed)
- _event_to_finding uses typed loading and redacts secrets
- Adversarial: duplicate task IDs, conflicting observations, near-secret content
- Adversarial: malformed payloads (non-dict, None, missing required fields)
- Adversarial: blocked tasks contribute only errors, not observations/summary
- merge_subagent_findings deduplicates and caps correctly under adversarial input
- AgentJournalStore.record_subagent_dispatch adds payload_version=1
- Old journals without payload_version still load correctly via findings_from_journal_events
"""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock

import pytest

from safecode.subagents.payload import (
    CURRENT_PAYLOAD_VERSION,
    SUPPORTED_PAYLOAD_VERSIONS,
    SubagentDispatchPayload,
)


# ---------------------------------------------------------------------------
# SubagentDispatchPayload model tests
# ---------------------------------------------------------------------------

class TestSubagentDispatchPayload:
    def test_defaults(self):
        p = SubagentDispatchPayload()
        assert p.payload_version == 1
        assert p.task_id == ""
        assert p.summary == ""
        assert p.observations == []
        assert p.files_inspected == []
        assert p.errors == []
        assert p.blocked is False
        assert p.success is False

    def test_current_payload_version(self):
        # v3.4.3: CURRENT_PAYLOAD_VERSION bumped to 2; v1 still supported.
        assert CURRENT_PAYLOAD_VERSION == 2
        assert 2 in SUPPORTED_PAYLOAD_VERSIONS
        assert 1 in SUPPORTED_PAYLOAD_VERSIONS  # backward compat

    def test_full_payload(self):
        p = SubagentDispatchPayload(
            payload_version=1,
            task_id="task-abc",
            summary="found 3 issues",
            observations=["obs1", "obs2"],
            files_inspected=["src/foo.py"],
            errors=[],
            blocked=False,
            success=True,
        )
        assert p.task_id == "task-abc"
        assert p.success is True
        assert len(p.observations) == 2

    def test_old_journal_no_payload_version_defaults_to_1(self):
        raw = {
            "task_id": "old-task",
            "summary": "old summary",
            "observations": ["old obs"],
            "files_inspected": [],
            "errors": [],
            "blocked": False,
            "success": True,
        }
        p = SubagentDispatchPayload.model_validate(raw)
        assert p.payload_version == 1

    def test_extra_fields_ignored(self):
        raw = {
            "task_id": "t1",
            "summary": "s",
            "extra_unknown_field": "should be ignored",
        }
        p = SubagentDispatchPayload.model_validate(raw)
        assert p.task_id == "t1"
        assert not hasattr(p, "extra_unknown_field")

    def test_blocked_task_default(self):
        p = SubagentDispatchPayload(task_id="t", blocked=True, success=False)
        assert p.blocked is True
        assert p.success is False

    def test_version_2_is_supported(self):
        # v3.4.3: payload v2 promoted to supported.
        assert 2 in SUPPORTED_PAYLOAD_VERSIONS


# ---------------------------------------------------------------------------
# _event_to_finding: old journal backward compatibility
# ---------------------------------------------------------------------------

class TestEventToFindingOldJournalCompat:
    def _make_event(self, payload_inner: object) -> "AgentJournalEvent":
        from safecode.state.journal import AgentJournalEvent
        return AgentJournalEvent(
            session_id="test-session-0001",
            type="subagent_dispatch",
            message="dispatched",
            payload={"subagent_dispatch": payload_inner},
        )

    def test_old_journal_no_version_parses(self):
        from safecode.subagents.journal_adapter import _event_to_finding

        event = self._make_event({
            "task_id": "old-task",
            "summary": "old summary",
            "observations": ["obs"],
            "files_inspected": ["file.py"],
            "errors": [],
            "blocked": False,
            "success": True,
        })
        finding = _event_to_finding(event)
        assert finding is not None
        assert finding.task_id == "old-task"
        assert finding.success is True

    def test_new_journal_with_version_parses(self):
        from safecode.subagents.journal_adapter import _event_to_finding

        event = self._make_event({
            "payload_version": 1,
            "task_id": "new-task",
            "summary": "new summary",
            "observations": ["obs1"],
            "files_inspected": [],
            "errors": [],
            "blocked": False,
            "success": True,
        })
        finding = _event_to_finding(event)
        assert finding is not None
        assert finding.task_id == "new-task"

    def test_non_dict_payload_returns_none(self):
        from safecode.subagents.journal_adapter import _event_to_finding

        event = self._make_event("not a dict")
        assert _event_to_finding(event) is None

    def test_none_payload_returns_none(self):
        from safecode.subagents.journal_adapter import _event_to_finding

        event = self._make_event(None)
        assert _event_to_finding(event) is None

    def test_non_subagent_dispatch_event_skipped(self):
        from safecode.state.journal import AgentJournalEvent
        from safecode.subagents.journal_adapter import findings_from_journal_events

        event = AgentJournalEvent(
            session_id="test-session-0001",
            type="plan",
            message="planning",
            payload={"goal": "test"},
        )
        findings = findings_from_journal_events([event])
        assert findings == []

    def test_missing_subagent_dispatch_key(self):
        from safecode.state.journal import AgentJournalEvent
        from safecode.subagents.journal_adapter import _event_to_finding

        event = AgentJournalEvent(
            session_id="test-session-0001",
            type="subagent_dispatch",
            message="dispatched",
            payload={"other_key": {}},
        )
        assert _event_to_finding(event) is None


# ---------------------------------------------------------------------------
# Unsupported version handling
# ---------------------------------------------------------------------------

class TestUnsupportedVersion:
    def _make_versioned_event(self, version: int) -> "AgentJournalEvent":
        from safecode.state.journal import AgentJournalEvent
        return AgentJournalEvent(
            session_id="test-session-0001",
            type="subagent_dispatch",
            message="dispatched",
            payload={"subagent_dispatch": {
                "payload_version": version,
                "task_id": "t",
                "summary": "s",
                "success": True,
            }},
        )

    def test_version_1_accepted(self):
        from safecode.subagents.journal_adapter import _event_to_finding

        event = self._make_versioned_event(1)
        finding = _event_to_finding(event)
        assert finding is not None

    def test_future_version_emits_warning_and_returns_none(self):
        from safecode.subagents.journal_adapter import _event_to_finding

        event = self._make_versioned_event(99)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _event_to_finding(event)
        assert result is None
        assert any(issubclass(warning.category, RuntimeWarning) for warning in w)
        assert any("99" in str(warning.message) for warning in w)

    def test_future_version_fail_closed(self):
        from safecode.subagents.journal_adapter import findings_from_journal_events

        # v1 and v2 are supported; v99 is unsupported future.
        events = [self._make_versioned_event(1), self._make_versioned_event(2), self._make_versioned_event(99)]
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            findings = findings_from_journal_events(events)
        # v1 and v2 events are included; v99 is skipped fail-closed.
        assert len(findings) == 2


# ---------------------------------------------------------------------------
# record_subagent_dispatch adds payload_version
# ---------------------------------------------------------------------------

class TestJournalStoreDispatchVersion:
    def test_record_adds_payload_version(self, tmp_path):
        from safecode.state.journal import AgentJournalStore

        store = AgentJournalStore(tmp_path)
        event = store.record_subagent_dispatch(
            session_id="test-session-0001",
            step=1,
            message="dispatched",
            dispatch_summary={
                "task_id": "t1",
                "summary": "s",
                "success": True,
                "blocked": False,
            },
        )
        payload = event.payload["subagent_dispatch"]
        assert isinstance(payload, dict)
        # v3.4.3: new payloads write CURRENT_PAYLOAD_VERSION (2).
        assert payload.get("payload_version") == 2

    def test_record_does_not_override_existing_version(self, tmp_path):
        from safecode.state.journal import AgentJournalStore

        store = AgentJournalStore(tmp_path)
        event = store.record_subagent_dispatch(
            session_id="test-session-0001",
            step=1,
            message="dispatched",
            dispatch_summary={
                "task_id": "t1",
                "payload_version": 1,
                "success": True,
            },
        )
        payload = event.payload["subagent_dispatch"]
        # If caller explicitly sets payload_version=1, it is preserved.
        assert payload["payload_version"] == 1

    def test_roundtrip_read_write(self, tmp_path):
        from safecode.state.journal import AgentJournalStore
        from safecode.subagents.journal_adapter import findings_from_journal_events

        store = AgentJournalStore(tmp_path)
        store.record_subagent_dispatch(
            session_id="test-session-0001",
            step=1,
            message="dispatched",
            dispatch_summary={
                "task_id": "task-xyz",
                "summary": "found 2 items",
                "observations": ["obs-a", "obs-b"],
                "files_inspected": ["src/main.py"],
                "errors": [],
                "blocked": False,
                "success": True,
            },
        )
        events = store.read("test-session-0001")
        findings = findings_from_journal_events(events)
        assert len(findings) == 1
        assert findings[0].task_id == "task-xyz"
        assert findings[0].success is True


# ---------------------------------------------------------------------------
# Adversarial tests (v2.9.7 folded in)
# ---------------------------------------------------------------------------

class TestAdversarialPayloads:
    """Adversarial merge tests: duplicate IDs, conflicting observations, malformed."""

    def _make_event(self, payload_inner: object) -> "AgentJournalEvent":
        from safecode.state.journal import AgentJournalEvent
        return AgentJournalEvent(
            session_id="adv-session-0001",
            type="subagent_dispatch",
            message="adversarial",
            payload={"subagent_dispatch": payload_inner},
        )

    def test_duplicate_task_ids_both_processed(self):
        from safecode.subagents.journal_adapter import findings_from_journal_events
        from safecode.subagents.merge_policy import merge_subagent_findings

        events = [
            self._make_event({"task_id": "dup-task", "summary": "first", "success": True, "blocked": False}),
            self._make_event({"task_id": "dup-task", "summary": "second", "success": True, "blocked": False}),
        ]
        findings = findings_from_journal_events(events)
        assert len(findings) == 2

        merged = merge_subagent_findings(findings)
        # Both task_ids contribute to source_task_ids (dedup is observation-level, not task-level)
        assert merged.source_task_ids.count("dup-task") == 2

    def test_conflicting_observations_deduplicated_by_merge(self):
        from safecode.subagents.journal_adapter import findings_from_journal_events
        from safecode.subagents.merge_policy import merge_subagent_findings

        events = [
            self._make_event({
                "task_id": "t1", "summary": "s1",
                "observations": ["obs-shared", "obs-unique-1"],
                "success": True, "blocked": False,
            }),
            self._make_event({
                "task_id": "t2", "summary": "s2",
                "observations": ["obs-shared", "obs-unique-2"],
                "success": True, "blocked": False,
            }),
        ]
        findings = findings_from_journal_events(events)
        merged = merge_subagent_findings(findings)
        # "obs-shared" should appear only once
        assert merged.observations.count("obs-shared") == 1
        assert "obs-unique-1" in merged.observations
        assert "obs-unique-2" in merged.observations

    def test_near_secret_content_is_redacted(self):
        from safecode.subagents.journal_adapter import _event_to_finding

        event = self._make_event({
            "task_id": "t",
            "summary": "token=ghp_exampletoken123456789012345678901234",
            "observations": ["api_key=sk-abcdefghijklmnopqrstuvwxyz12345678"],
            "files_inspected": [],
            "errors": [],
            "success": True,
            "blocked": False,
        })
        finding = _event_to_finding(event)
        assert finding is not None
        assert "REDACTED" in finding.summary or finding.summary != "token=ghp_exampletoken123456789012345678901234"

    def test_malformed_observations_non_list(self):
        from safecode.subagents.journal_adapter import _event_to_finding

        # observations is a string instead of a list
        event = self._make_event({
            "task_id": "t",
            "summary": "s",
            "observations": "not a list",
            "success": True,
            "blocked": False,
        })
        # Pydantic will coerce or reject; the key is we don't crash
        result = _event_to_finding(event)
        # Either None (rejected) or a valid finding with empty/coerced observations
        assert result is None or isinstance(result.observations, list)

    def test_malformed_payload_empty_dict(self):
        from safecode.subagents.journal_adapter import _event_to_finding

        event = self._make_event({})
        # All fields default → should produce a valid finding with defaults
        result = _event_to_finding(event)
        assert result is not None
        assert result.task_id == ""
        assert result.success is False

    def test_blocked_task_does_not_contribute_observations_to_merge(self):
        from safecode.subagents.journal_adapter import findings_from_journal_events
        from safecode.subagents.merge_policy import merge_subagent_findings

        events = [
            self._make_event({
                "task_id": "blocked-task", "summary": "secret stuff",
                "observations": ["sensitive obs"], "errors": ["blocked by policy"],
                "success": False, "blocked": True,
            }),
            self._make_event({
                "task_id": "good-task", "summary": "good result",
                "observations": ["safe obs"],
                "success": True, "blocked": False,
            }),
        ]
        findings = findings_from_journal_events(events)
        merged = merge_subagent_findings(findings)
        assert "sensitive obs" not in merged.observations
        assert "safe obs" in merged.observations
        assert "blocked-task" in merged.blocked_task_ids
        assert "good-task" in merged.source_task_ids

    def test_max_observations_cap(self):
        from safecode.subagents.journal_adapter import findings_from_journal_events
        from safecode.subagents.merge_policy import merge_subagent_findings

        obs_list = [f"obs-{i}" for i in range(30)]
        events = [self._make_event({
            "task_id": "big-task",
            "observations": obs_list,
            "success": True, "blocked": False,
        })]
        findings = findings_from_journal_events(events)
        merged = merge_subagent_findings(findings, max_observations=10)
        assert len(merged.observations) == 10

    def test_all_blocked_findings_returns_empty_observations(self):
        from safecode.subagents.journal_adapter import findings_from_journal_events
        from safecode.subagents.merge_policy import merge_subagent_findings

        events = [
            self._make_event({"task_id": f"blocked-{i}", "blocked": True, "success": False,
                              "observations": ["obs"], "errors": [f"err-{i}"]})
            for i in range(3)
        ]
        findings = findings_from_journal_events(events)
        merged = merge_subagent_findings(findings)
        assert merged.observations == []
        assert len(merged.blocked_task_ids) == 3
        assert len(merged.errors) == 3

    def test_empty_task_id_skipped_in_merge(self):
        from safecode.subagents.journal_adapter import findings_from_journal_events
        from safecode.subagents.merge_policy import merge_subagent_findings

        events = [
            self._make_event({"task_id": "", "summary": "no id", "success": True, "blocked": False}),
        ]
        findings = findings_from_journal_events(events)
        merged = merge_subagent_findings(findings)
        # Empty task_id is silently skipped in source_task_ids
        assert "" not in merged.source_task_ids

    def test_list_of_events_with_mixed_types(self):
        from safecode.state.journal import AgentJournalEvent
        from safecode.subagents.journal_adapter import findings_from_journal_events

        events = [
            AgentJournalEvent(
                session_id="adv-session-0001", type="plan",
                message="plan", payload={"goal": "x"},
            ),
            self._make_event({"task_id": "t1", "success": True, "blocked": False}),
            AgentJournalEvent(
                session_id="adv-session-0001", type="action",
                message="step", payload={},
            ),
            self._make_event({"task_id": "t2", "success": False, "blocked": True}),
        ]
        findings = findings_from_journal_events(events)
        assert len(findings) == 2

    def test_findings_from_journal_events_never_raises(self):
        from safecode.subagents.journal_adapter import findings_from_journal_events

        # Inject events that would cause errors at various points
        malformed_events = [
            self._make_event(None),
            self._make_event("bad"),
            self._make_event([]),
            self._make_event({"payload_version": 999, "task_id": "t"}),
        ]
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = findings_from_journal_events(malformed_events)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# v2 payload tests (T-3.4.3-A)
# ---------------------------------------------------------------------------


class TestPayloadV2Fields:
    """v2 payload: synthesis + cancellation fields round-trip (T-3.4.3-A)."""

    def test_v2_payload_loads_with_synthesis_fields(self):
        raw = {
            "payload_version": 2,
            "task_id": "v2-task",
            "summary": "v2 summary",
            "observations": [],
            "files_inspected": [],
            "errors": [],
            "blocked": False,
            "success": True,
            "synthesis_summary": "synthesized text",
            "synthesis_key_findings": ["finding A", "finding B"],
            "synthesis_risks": ["risk 1"],
            "synthesis_source_task_ids": ["v2-task"],
            "cancelled_task_ids": [],
        }
        p = SubagentDispatchPayload.model_validate(raw)
        assert p.payload_version == 2
        assert p.synthesis_summary == "synthesized text"
        assert p.synthesis_key_findings == ["finding A", "finding B"]
        assert p.synthesis_risks == ["risk 1"]
        assert p.synthesis_source_task_ids == ["v2-task"]
        assert p.cancelled_task_ids == []

    def test_v1_loads_with_empty_v2_defaults(self):
        """v1 payload still loads; new v2 fields default safely."""
        raw = {
            "payload_version": 1,
            "task_id": "v1-task",
            "summary": "v1 summary",
            "success": True,
            "blocked": False,
        }
        p = SubagentDispatchPayload.model_validate(raw)
        assert p.payload_version == 1
        assert p.synthesis_summary == ""
        assert p.synthesis_key_findings == []
        assert p.synthesis_risks == []
        assert p.synthesis_source_task_ids == []
        assert p.cancelled_task_ids == []

    def test_missing_optional_v2_fields_load_safely(self):
        """v2 payload with only core fields: optional v2 fields default."""
        raw = {
            "payload_version": 2,
            "task_id": "v2-partial",
            "success": True,
        }
        p = SubagentDispatchPayload.model_validate(raw)
        assert p.payload_version == 2
        assert p.synthesis_summary == ""
        assert p.cancelled_task_ids == []

    def test_cancellation_fields_round_trip(self):
        """cancelled_task_ids round-trips through model serialization."""
        p = SubagentDispatchPayload(
            payload_version=2,
            task_id="t",
            cancelled_task_ids=["cancelled-1", "cancelled-2"],
        )
        dumped = p.model_dump()
        reloaded = SubagentDispatchPayload.model_validate(dumped)
        assert reloaded.cancelled_task_ids == ["cancelled-1", "cancelled-2"]

    def test_v2_synthesis_round_trip_via_model_dump(self):
        """v2 synthesis fields survive model_dump → model_validate round-trip."""
        p = SubagentDispatchPayload(
            payload_version=2,
            task_id="synth-task",
            synthesis_summary="key insight",
            synthesis_key_findings=["finding 1", "finding 2"],
            synthesis_risks=["possible risk"],
            synthesis_source_task_ids=["synth-task"],
        )
        dumped = p.model_dump()
        assert dumped["payload_version"] == 2
        assert dumped["synthesis_summary"] == "key insight"
        reloaded = SubagentDispatchPayload.model_validate(dumped)
        assert reloaded.synthesis_summary == "key insight"
        assert reloaded.synthesis_key_findings == ["finding 1", "finding 2"]

    def test_v2_extra_fields_ignored(self):
        """Unknown future fields are silently ignored (extra='ignore')."""
        raw = {
            "payload_version": 2,
            "task_id": "t",
            "synthesis_summary": "s",
            "future_unknown_field": "should be ignored",
        }
        p = SubagentDispatchPayload.model_validate(raw)
        assert p.synthesis_summary == "s"
        assert not hasattr(p, "future_unknown_field")


class TestPayloadV2JournalRoundTrip:
    """v2 payload round-trips through AgentJournalStore write/read."""

    def test_v2_writes_payload_version_2(self, tmp_path):
        from safecode.state.journal import AgentJournalStore
        from safecode.subagents.payload import CURRENT_PAYLOAD_VERSION

        assert CURRENT_PAYLOAD_VERSION == 2

        store = AgentJournalStore(tmp_path)
        event = store.record_subagent_dispatch(
            session_id="v2-session-001",
            step=1,
            message="v2 dispatch",
            dispatch_summary={
                "task_id": "t-v2",
                "summary": "v2 summary",
                "success": True,
                "blocked": False,
                "synthesis_summary": "parent synthesis",
                "synthesis_key_findings": ["key A"],
                "cancelled_task_ids": [],
            },
        )
        payload = event.payload["subagent_dispatch"]
        assert payload["payload_version"] == 2
        assert payload["synthesis_summary"] == "parent synthesis"

    def test_v2_synthesis_fields_persist_in_journal(self, tmp_path):
        from safecode.state.journal import AgentJournalStore

        store = AgentJournalStore(tmp_path)
        store.record_subagent_dispatch(
            session_id="v2-session-002",
            step=1,
            message="v2 with synthesis",
            dispatch_summary={
                "task_id": "t-synth",
                "success": True,
                "blocked": False,
                "synthesis_summary": "synthesized result",
                "synthesis_key_findings": ["kf1", "kf2"],
                "synthesis_risks": ["risk A"],
                "synthesis_source_task_ids": ["t-synth"],
                "cancelled_task_ids": [],
            },
        )
        events = store.read("v2-session-002")
        assert len(events) == 1
        payload = events[0].payload["subagent_dispatch"]
        assert payload["payload_version"] == 2
        assert payload["synthesis_summary"] == "synthesized result"
        assert payload["synthesis_key_findings"] == ["kf1", "kf2"]

    def test_v1_still_loads_from_journal(self, tmp_path):
        """Writing a v1 payload to journal and reading back works."""
        from safecode.state.journal import AgentJournalStore
        from safecode.subagents.journal_adapter import findings_from_journal_events

        store = AgentJournalStore(tmp_path)
        store.record_subagent_dispatch(
            session_id="v1-compat-session",
            step=1,
            message="v1 compat",
            dispatch_summary={
                "payload_version": 1,
                "task_id": "legacy-task",
                "summary": "legacy summary",
                "success": True,
                "blocked": False,
            },
        )
        events = store.read("v1-compat-session")
        findings = findings_from_journal_events(events)
        assert len(findings) == 1
        assert findings[0].task_id == "legacy-task"
        assert findings[0].success is True


class TestPayloadV2UnsupportedFutureVersion:
    """Unsupported future versions fail closed (T-3.4.3-A)."""

    def _make_event(self, version: int) -> "AgentJournalEvent":
        from safecode.state.journal import AgentJournalEvent
        return AgentJournalEvent(
            session_id="future-session",
            type="subagent_dispatch",
            message="future",
            payload={"subagent_dispatch": {
                "payload_version": version,
                "task_id": "t",
                "summary": "s",
                "success": True,
            }},
        )

    def test_version_3_warns_and_skips(self):
        from safecode.subagents.journal_adapter import _event_to_finding

        event = self._make_event(3)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _event_to_finding(event)
        assert result is None
        assert any(issubclass(warning.category, RuntimeWarning) for warning in w)

    def test_malformed_payload_warning_does_not_leak_secrets(self):
        """Warning text must not contain caller-supplied content or secrets."""
        from safecode.state.journal import AgentJournalEvent
        from safecode.subagents.journal_adapter import _event_to_finding

        secret = "sk-secretvalue12345678901234567890"
        event = AgentJournalEvent(
            session_id="secret-session",
            type="subagent_dispatch",
            message="secret payload",
            payload={"subagent_dispatch": {
                "payload_version": 999,
                "task_id": secret,
                "summary": f"api_key={secret}",
            }},
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _event_to_finding(event)
        for warning in w:
            msg = str(warning.message)
            assert secret not in msg, f"Secret leaked in warning: {msg}"

    def test_unsupported_version_does_not_crash_normal_runs(self):
        """A journal with a mix of supported and unsupported events continues."""
        from safecode.subagents.journal_adapter import findings_from_journal_events

        events = [
            self._make_event(1),
            self._make_event(2),
            self._make_event(999),
        ]
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            findings = findings_from_journal_events(events)
        # v1 and v2 parsed; v999 skipped
        assert len(findings) == 2
