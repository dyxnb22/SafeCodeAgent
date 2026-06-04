"""Tests for sac history --task filter and AuditLogger.read_by_task_id (v4.1.2 T-4.1.2-A)."""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.utils.time import utc_now_iso


def _write(logger: AuditLogger, event_type: str, task_id: str | None = None) -> AuditEvent:
    event = AuditEvent(type=event_type, timestamp=utc_now_iso())
    logger.write(event, task_id=task_id)
    return event


class TestAuditLoggerReadByTaskId:
    def test_returns_matching_events(self, tmp_path):
        logger = AuditLogger(tmp_path)
        _write(logger, "patch_proposed", task_id="task-abc12345")
        _write(logger, "other_event")
        _write(logger, "patch_applied", task_id="task-abc12345")
        results = logger.read_by_task_id("task-abc12345")
        assert len(results) == 2
        types = {e.type for e in results}
        assert "patch_proposed" in types
        assert "patch_applied" in types
        assert "other_event" not in types

    def test_returns_empty_for_unknown_id(self, tmp_path):
        logger = AuditLogger(tmp_path)
        _write(logger, "patch_proposed", task_id="task-abc12345")
        results = logger.read_by_task_id("completely-unknown-task")
        assert results == []

    def test_no_log_file_returns_empty(self, tmp_path):
        logger = AuditLogger(tmp_path)
        results = logger.read_by_task_id("any-task-id")
        assert results == []

    def test_empty_task_id_returns_empty(self, tmp_path):
        logger = AuditLogger(tmp_path)
        _write(logger, "patch_proposed", task_id="task-abc12345")
        results = logger.read_by_task_id("")
        assert results == []

    def test_exact_match_not_prefix(self, tmp_path):
        logger = AuditLogger(tmp_path)
        _write(logger, "event_a", task_id="task-abc12345")
        _write(logger, "event_b", task_id="task-abc12345-suffix")
        results = logger.read_by_task_id("task-abc12345")
        assert len(results) == 1
        assert results[0].type == "event_a"

    def test_limit_respected(self, tmp_path):
        logger = AuditLogger(tmp_path)
        for i in range(10):
            _write(logger, f"event_{i}", task_id="task-abc12345")
        results = logger.read_by_task_id("task-abc12345", limit=3)
        assert len(results) == 3

    def test_result_is_deterministic(self, tmp_path):
        logger = AuditLogger(tmp_path)
        _write(logger, "event_first", task_id="task-abc12345")
        _write(logger, "event_second", task_id="task-abc12345")
        r1 = logger.read_by_task_id("task-abc12345")
        r2 = logger.read_by_task_id("task-abc12345")
        assert [e.type for e in r1] == [e.type for e in r2]

    def test_events_without_task_id_excluded(self, tmp_path):
        logger = AuditLogger(tmp_path)
        _write(logger, "event_no_task")
        _write(logger, "event_with_task", task_id="task-abc12345")
        results = logger.read_by_task_id("task-abc12345")
        assert len(results) == 1
        assert results[0].type == "event_with_task"

    def test_corrupted_lines_skipped(self, tmp_path):
        logger = AuditLogger(tmp_path)
        _write(logger, "good_event", task_id="task-abc12345")
        # Append a corrupted line directly
        log_file = tmp_path / ".sac" / "logs" / "events.jsonl"
        with log_file.open("a") as f:
            f.write("{corrupt json\n")
        results = logger.read_by_task_id("task-abc12345")
        # Corrupted lines are skipped, good events still returned
        assert any(e.type == "good_event" for e in results)

    def test_returns_redactable_events(self, tmp_path):
        """read_by_task_id returns raw events; caller must redact."""
        logger = AuditLogger(tmp_path)
        _write(logger, "shell_completed", task_id="task-abc12345")
        results = logger.read_by_task_id("task-abc12345")
        assert results  # Events are returned for caller to redact
