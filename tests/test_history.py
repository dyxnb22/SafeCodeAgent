"""Tests for sac history command (baseline + task filter, v4.1.2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.cli import app
from safecode.utils.time import utc_now_iso

runner = CliRunner()


def _write_event(logger: AuditLogger, event_type: str, task_id: str | None = None) -> None:
    event = AuditEvent(type=event_type, timestamp=utc_now_iso())
    logger.write(event, task_id=task_id)


class TestHistoryBaseline:
    def test_history_no_events(self, tmp_path):
        with patch("safecode.cli_core.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["history"])
        assert result.exit_code == 0
        assert "No audit events found" in result.output

    def test_history_shows_events(self, tmp_path):
        logger = AuditLogger(tmp_path)
        _write_event(logger, "patch_proposed")
        with patch("safecode.cli_core.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["history"])
        assert result.exit_code == 0
        # Rich truncates long strings in narrow terminals; check unambiguous prefix
        assert "patch_propo" in result.output

    def test_history_multiple_events(self, tmp_path):
        logger = AuditLogger(tmp_path)
        for etype in ("patch_proposed", "patch_applied", "rollback_completed"):
            _write_event(logger, etype)
        with patch("safecode.cli_core.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["history"])
        assert result.exit_code == 0
        # Rich truncates long strings in narrow terminals; check unambiguous prefixes
        assert "patch_propo" in result.output
        assert "patch_appli" in result.output


class TestHistoryTaskFilter:
    def test_filter_by_task_id_returns_matching(self, tmp_path):
        logger = AuditLogger(tmp_path)
        _write_event(logger, "patch_proposed", task_id="task-abc12345")
        _write_event(logger, "other_event")
        with patch("safecode.cli_core.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["history", "--task", "task-abc12345"])
        assert result.exit_code == 0
        # Rich truncates long strings in narrow terminals; check unambiguous prefix
        assert "patch_propo" in result.output

    def test_filter_unknown_task_returns_empty(self, tmp_path):
        logger = AuditLogger(tmp_path)
        _write_event(logger, "patch_proposed", task_id="task-abc12345")
        with patch("safecode.cli_core.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["history", "--task", "unknown-task-id"])
        assert result.exit_code == 0
        assert "No audit events found" in result.output

    def test_filter_no_log_returns_empty(self, tmp_path):
        with patch("safecode.cli_core.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["history", "--task", "some-task"])
        assert result.exit_code == 0
        assert "No audit events found" in result.output

    def test_filter_exact_match_only(self, tmp_path):
        logger = AuditLogger(tmp_path)
        _write_event(logger, "event_a", task_id="task-abc12345")
        _write_event(logger, "event_b", task_id="task-xyz99999")
        with patch("safecode.cli_core.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = runner.invoke(app, ["history", "--task", "task-abc12345"])
        assert result.exit_code == 0
        assert "event_a" in result.output
        assert "event_b" not in result.output
