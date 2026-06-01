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
