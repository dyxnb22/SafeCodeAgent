"""Tests for v2.7.3 subagent-finding-redaction-logging."""

import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.loop import AgentLoop
from safecode.config import SafeCodeConfig


def _make_loop(tmp_path: Path) -> AgentLoop:
    with patch("safecode.agent.loop.SafeCodeConfig") as mock_cfg_cls:
        mock_cfg_cls.load.return_value = SafeCodeConfig()
        loop = AgentLoop(project_root=tmp_path)
    return loop


class TestSubagentFindingRedaction:
    def test_api_key_in_summary_is_redacted(self, tmp_path):
        loop = _make_loop(tmp_path)
        merged = MagicMock()
        merged.source_task_ids = ["task-1"]
        merged.blocked_task_ids = []
        merged.errors = []
        merged.summary = 'Found api_key = "sk-supersecretvalue123456789"'
        merged.observations = []
        merged.files_inspected = []

        with patch("safecode.agent.loop.merge_journal_subagent_findings", return_value=merged):
            with patch.object(loop.journal, "read", return_value=[]):
                context = loop._enrich_with_subagent_findings("session-1", {})

        assert "sk-supersecretvalue" not in context["subagent_findings"]["summary"]
        assert "[REDACTED]" in context["subagent_findings"]["summary"]

    def test_bearer_token_in_observation_is_redacted(self, tmp_path):
        loop = _make_loop(tmp_path)
        merged = MagicMock()
        merged.source_task_ids = ["task-1"]
        merged.blocked_task_ids = []
        merged.errors = []
        merged.summary = "clean summary"
        merged.observations = ["Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"]
        merged.files_inspected = []

        with patch("safecode.agent.loop.merge_journal_subagent_findings", return_value=merged):
            with patch.object(loop.journal, "read", return_value=[]):
                context = loop._enrich_with_subagent_findings("session-1", {})

        obs = context["subagent_findings"]["observations"][0]
        assert "eyJhbGci" not in obs
        assert "[REDACTED]" in obs

    def test_jwt_in_error_message_is_redacted(self, tmp_path):
        loop = _make_loop(tmp_path)
        merged = MagicMock()
        merged.source_task_ids = []
        merged.blocked_task_ids = []
        merged.errors = ["token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c failed"]
        merged.summary = ""
        merged.observations = []
        merged.files_inspected = []

        with patch("safecode.agent.loop.merge_journal_subagent_findings", return_value=merged):
            with patch.object(loop.journal, "read", return_value=[]):
                context = loop._enrich_with_subagent_findings("session-1", {})

        err = context["subagent_findings"]["errors"][0]
        assert "eyJhbGci" not in err
        assert "[REDACTED]" in err

    def test_clean_findings_pass_through_unchanged(self, tmp_path):
        loop = _make_loop(tmp_path)
        merged = MagicMock()
        merged.source_task_ids = ["task-1"]
        merged.blocked_task_ids = []
        merged.errors = []
        merged.summary = "Found 3 Python files with unused imports."
        merged.observations = ["module foo has unused import bar"]
        merged.files_inspected = ["foo.py"]

        with patch("safecode.agent.loop.merge_journal_subagent_findings", return_value=merged):
            with patch.object(loop.journal, "read", return_value=[]):
                context = loop._enrich_with_subagent_findings("session-1", {})

        assert context["subagent_findings"]["summary"] == "Found 3 Python files with unused imports."
        assert context["subagent_findings"]["observations"] == ["module foo has unused import bar"]

    def test_enrichment_error_emits_warning_not_exception(self, tmp_path):
        loop = _make_loop(tmp_path)

        with patch.object(loop.journal, "read", side_effect=RuntimeError("journal broken")):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                context = loop._enrich_with_subagent_findings("session-1", {"existing": "data"})

        assert context == {"existing": "data"}
        runtime_warns = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        assert runtime_warns, "expected a RuntimeWarning on enrichment failure"
        assert "subagent enrichment failed" in str(runtime_warns[0].message)

    def test_enrichment_error_does_not_clear_existing_context(self, tmp_path):
        loop = _make_loop(tmp_path)
        initial_context = {"project_root": "/tmp/test", "goal": "do something"}

        with patch.object(loop.journal, "read", side_effect=ValueError("bad data")):
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = loop._enrich_with_subagent_findings("s1", initial_context.copy())

        assert result["project_root"] == "/tmp/test"
        assert result["goal"] == "do something"
        assert "subagent_findings" not in result


# ---------------------------------------------------------------------------
# v2.8.7: producer-side redaction at journal boundary
# ---------------------------------------------------------------------------

from safecode.subagents.journal_adapter import _event_to_finding, findings_from_journal_events
from safecode.state.journal import AgentJournalEvent


def _make_dispatch_event(payload: dict) -> AgentJournalEvent:
    return AgentJournalEvent(
        session_id="sess-1",
        step=0,
        type="subagent_dispatch",
        message="subagent dispatch",
        payload={"subagent_dispatch": payload},
    )


class TestJournalBoundaryRedaction:
    """Producer-side redaction in _event_to_finding (v2.8.7)."""

    def test_api_key_in_summary_redacted_at_boundary(self):
        event = _make_dispatch_event({
            "task_id": "t1",
            "summary": 'api_key = "sk-verysecret12345678901234"',
            "observations": [],
            "files_inspected": [],
            "errors": [],
            "success": True,
            "blocked": False,
        })
        finding = _event_to_finding(event)
        assert finding is not None
        assert "sk-verysecret" not in finding.summary
        assert "[REDACTED]" in finding.summary

    def test_bearer_token_in_observation_redacted_at_boundary(self):
        event = _make_dispatch_event({
            "task_id": "t1",
            "summary": "clean",
            "observations": [
                "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
                ".eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36P"
            ],
            "files_inspected": [],
            "errors": [],
            "success": True,
            "blocked": False,
        })
        finding = _event_to_finding(event)
        assert finding is not None
        assert "eyJhbGci" not in finding.observations[0]
        assert "[REDACTED]" in finding.observations[0]

    def test_secret_in_error_redacted_at_boundary(self):
        event = _make_dispatch_event({
            "task_id": "t1",
            "summary": "clean",
            "observations": [],
            "files_inspected": [],
            "errors": ['token = "ghp_abc123def456ghi789jkl012mno345pqr"'],
            "success": False,
            "blocked": False,
        })
        finding = _event_to_finding(event)
        assert finding is not None
        assert "ghp_abc" not in finding.errors[0]
        assert "[REDACTED]" in finding.errors[0]

    def test_clean_content_passes_through_unchanged(self):
        event = _make_dispatch_event({
            "task_id": "t1",
            "summary": "Found 3 unused imports.",
            "observations": ["module foo imports bar which is unused"],
            "files_inspected": ["foo.py"],
            "errors": [],
            "success": True,
            "blocked": False,
        })
        finding = _event_to_finding(event)
        assert finding is not None
        assert finding.summary == "Found 3 unused imports."
        assert finding.observations == ["module foo imports bar which is unused"]
        assert finding.files_inspected == ["foo.py"]

    def test_already_redacted_content_stays_redacted(self):
        # Already-redacted content must not re-introduce the secret or crash.
        event = _make_dispatch_event({
            "task_id": "t1",
            "summary": "no secrets here, just code review findings",
            "observations": ["file foo.py has unused imports"],
            "files_inspected": [],
            "errors": [],
            "success": True,
            "blocked": False,
        })
        finding = _event_to_finding(event)
        assert finding is not None
        # Applying redaction twice on clean text must not corrupt it.
        from safecode.context.redactor import redact_secrets
        once = redact_secrets(finding.summary)
        twice = redact_secrets(once)
        assert twice == once, "double-redact must be stable on already-clean text"

    def test_malformed_payload_returns_none(self):
        event = AgentJournalEvent(
            session_id="sess-1",
            step=0,
            type="subagent_dispatch",
            message="subagent dispatch",
            payload={"subagent_dispatch": "not-a-dict"},
        )
        assert _event_to_finding(event) is None

    def test_files_inspected_not_redacted(self):
        event = _make_dispatch_event({
            "task_id": "t1",
            "summary": "clean",
            "observations": [],
            "files_inspected": ["/path/to/config.py"],
            "errors": [],
            "success": True,
            "blocked": False,
        })
        finding = _event_to_finding(event)
        assert finding is not None
        assert finding.files_inspected == ["/path/to/config.py"]

    def test_multiple_events_all_redacted(self):
        events = [
            _make_dispatch_event({
                "task_id": f"t{i}",
                "summary": f'token = "supersecret{i}0000000000000000000000"',
                "observations": [],
                "files_inspected": [],
                "errors": [],
                "success": True,
                "blocked": False,
            })
            for i in range(3)
        ]
        findings = findings_from_journal_events(events)
        assert len(findings) == 3
        for f in findings:
            assert "supersecret" not in f.summary
            assert "[REDACTED]" in f.summary


class TestConsumerSideRedactionWarning:
    """Loop warns when consumer-side redaction still changes merged text (v2.8.7)."""

    def test_loop_warns_if_consumer_side_changes_summary(self, tmp_path):
        loop = _make_loop(tmp_path)
        merged = MagicMock()
        merged.source_task_ids = ["task-1"]
        merged.blocked_task_ids = []
        merged.errors = []
        # Simulate producer-side redaction gap: secret reaches the consumer
        merged.summary = 'api_key = "sk-leaked12345678901234567890"'
        merged.observations = []
        merged.files_inspected = []

        with patch("safecode.agent.loop.merge_journal_subagent_findings", return_value=merged):
            with patch.object(loop.journal, "read", return_value=[]):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    context = loop._enrich_with_subagent_findings("session-1", {})

        runtime_warns = [w for w in caught if issubclass(w.category, RuntimeWarning)]
        warning_msgs = [str(w.message) for w in runtime_warns]
        assert any("consumer-side redaction changed" in m for m in warning_msgs), (
            f"Expected producer-gap warning, got: {warning_msgs}"
        )
        # Secret is still redacted in the final context
        assert "sk-leaked" not in context["subagent_findings"]["summary"]

    def test_loop_no_warning_when_producer_already_redacted(self, tmp_path):
        loop = _make_loop(tmp_path)
        merged = MagicMock()
        merged.source_task_ids = ["task-1"]
        merged.blocked_task_ids = []
        merged.errors = []
        merged.summary = "Found 3 unused imports."
        merged.observations = ["module foo imports bar"]
        merged.files_inspected = []

        with patch("safecode.agent.loop.merge_journal_subagent_findings", return_value=merged):
            with patch.object(loop.journal, "read", return_value=[]):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    loop._enrich_with_subagent_findings("session-1", {})

        producer_gap_warns = [
            w for w in caught
            if issubclass(w.category, RuntimeWarning) and "consumer-side redaction changed" in str(w.message)
        ]
        assert not producer_gap_warns, f"Unexpected warnings: {producer_gap_warns}"
