"""Tests for JSONL audit logging."""

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent


def test_write_creates_jsonl_event(tmp_path) -> None:
    logger = AuditLogger(tmp_path)
    event = AuditEvent(
        type="ask_completed",
        timestamp="2026-05-21T12:30:00Z",
        message="这个项目是什么？",
    )

    logger.write(event)

    log_file = tmp_path / ".sac" / "logs" / "events.jsonl"
    assert log_file.exists()
    assert "ask_completed" in log_file.read_text(encoding="utf-8")


def test_read_recent_returns_latest_events(tmp_path) -> None:
    logger = AuditLogger(tmp_path)
    logger.write(AuditEvent(type="first", timestamp="2026-05-21T12:30:00Z"))
    logger.write(AuditEvent(type="second", timestamp="2026-05-21T12:31:00Z"))

    events = logger.read_recent(limit=1)

    assert len(events) == 1
    assert events[0].type == "second"
