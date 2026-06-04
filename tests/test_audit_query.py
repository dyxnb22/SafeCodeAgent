"""Tests for experimental sac audit query."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.cli import app

runner = CliRunner()


def _write_event(tmp_path: Path, *, event_type: str, timestamp: str, task_id: str, message: str = "ok") -> None:
    AuditLogger(tmp_path).write(
        AuditEvent(
            type=event_type,
            timestamp=timestamp,
            status="success",
            message=message,
            metadata={"task_id": task_id},
        )
    )


def test_audit_logger_iter_events_reads_in_order(tmp_path) -> None:
    _write_event(tmp_path, event_type="one", timestamp="2026-01-01T00:00:00+00:00", task_id="task-1")
    _write_event(tmp_path, event_type="two", timestamp="2026-01-01T00:00:01+00:00", task_id="task-2")
    assert [event.type for event in AuditLogger(tmp_path).iter_events()] == ["one", "two"]


def test_query_filters_type_task_since_and_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_event(tmp_path, event_type="patch", timestamp="2026-01-01T00:00:00+00:00", task_id="task-1")
    _write_event(tmp_path, event_type="shell", timestamp="2026-01-02T00:00:00+00:00", task_id="task-2")
    _write_event(tmp_path, event_type="shell", timestamp="2026-01-03T00:00:00+00:00", task_id="task-2")
    result = runner.invoke(
        app,
        ["audit", "query", "--type", "shell", "--task", "task-2", "--since", "2026-01-02", "--limit", "1", "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["command"] == "audit query"
    assert data["data"]["count"] == 1
    assert data["data"]["events"][0]["timestamp"] == "2026-01-03T00:00:00+00:00"


def test_query_refuses_integrity_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_event(tmp_path, event_type="shell", timestamp="2026-01-01T00:00:00+00:00", task_id="task-1")
    log = tmp_path / ".sac" / "logs" / "events.jsonl"
    log.write_text(log.read_text(encoding="utf-8").replace("shell", "tampered"), encoding="utf-8")
    result = runner.invoke(app, ["audit", "query", "--json"], catch_exceptions=False)
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["status"] == "error"
    assert "integrity" in data["error"].lower() or "mismatch" in data["error"].lower()


def test_query_never_writes_audit_events(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_event(tmp_path, event_type="shell", timestamp="2026-01-01T00:00:00+00:00", task_id="task-1")
    log = tmp_path / ".sac" / "logs" / "events.jsonl"
    before = log.read_text(encoding="utf-8")
    result = runner.invoke(app, ["audit", "query", "--json"], catch_exceptions=False)
    assert result.exit_code == 0
    assert log.read_text(encoding="utf-8") == before


def test_query_json_redacts_message(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_event(
        tmp_path,
        event_type="shell",
        timestamp="2026-01-01T00:00:00+00:00",
        task_id="task-1",
        message="password=hunter2",
    )
    result = runner.invoke(app, ["audit", "query", "--json"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "hunter2" not in result.output


def test_query_invalid_since_returns_error(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["audit", "query", "--since", "not-a-date", "--json"], catch_exceptions=False)
    assert result.exit_code == 1
    assert json.loads(result.output)["status"] == "error"
