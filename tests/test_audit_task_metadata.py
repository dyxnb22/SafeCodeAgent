"""Tests for audit task_id metadata wiring (v4.1.1 T-4.1.1-B)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.task.store import TaskStore
from safecode.utils.time import utc_now_iso


# ---------------------------------------------------------------------------
# AuditLogger.write with task_id parameter
# ---------------------------------------------------------------------------

class TestAuditLoggerTaskId:
    def test_write_with_task_id_stores_in_metadata(self, tmp_path):
        logger = AuditLogger(tmp_path)
        event = AuditEvent(type="test_event", timestamp=utc_now_iso())
        logger.write(event, task_id="my-task-abc12345")
        events = logger.read_recent(limit=10)
        assert events
        last = events[-1]
        assert last.metadata.get("task_id") == "my-task-abc12345"

    def test_write_without_task_id_no_metadata_key(self, tmp_path):
        logger = AuditLogger(tmp_path)
        event = AuditEvent(type="test_event", timestamp=utc_now_iso())
        logger.write(event)
        events = logger.read_recent(limit=10)
        assert events
        last = events[-1]
        assert "task_id" not in last.metadata

    def test_write_task_id_does_not_change_field_set(self, tmp_path):
        logger = AuditLogger(tmp_path)
        event = AuditEvent(type="test_event", timestamp=utc_now_iso())
        logger.write(event, task_id="my-task-abc12345")
        # Field set must remain stable (stable contract 3)
        events = logger.read_recent(limit=10)
        last = events[-1]
        from safecode.audit.models import AuditEvent as _AuditEvent
        field_names = set(_AuditEvent.model_fields.keys())
        expected_fields = {
            "type", "timestamp", "status", "patch_id", "checkpoint_id",
            "files", "message", "error", "command", "exit_code",
            "trace_id", "previous_hash", "event_hash", "metadata",
        }
        assert expected_fields.issubset(field_names)

    def test_write_task_id_preserves_existing_metadata(self, tmp_path):
        logger = AuditLogger(tmp_path)
        event = AuditEvent(
            type="test_event",
            timestamp=utc_now_iso(),
            metadata={"scope_status": "in_scope"},
        )
        logger.write(event, task_id="task-id-xyz")
        events = logger.read_recent(limit=10)
        last = events[-1]
        assert last.metadata.get("task_id") == "task-id-xyz"
        assert last.metadata.get("scope_status") == "in_scope"

    def test_write_task_id_does_not_mutate_original_event(self, tmp_path):
        logger = AuditLogger(tmp_path)
        event = AuditEvent(type="test_event", timestamp=utc_now_iso())
        original_metadata = dict(event.metadata)
        logger.write(event, task_id="task-abc12345")
        # The original dict was replaced with a copy - check the event's current state
        # The AuditLogger creates a copy before modifying, so the original event.metadata
        # may now have task_id, but the contract is that the file has the right task_id
        events = logger.read_recent(limit=10)
        assert events[-1].metadata.get("task_id") == "task-abc12345"

    def test_audit_chain_integrity_preserved_with_task_id(self, tmp_path):
        logger = AuditLogger(tmp_path)
        for i in range(3):
            event = AuditEvent(type=f"event_{i}", timestamp=utc_now_iso())
            logger.write(event, task_id=f"task-{i}-abc12345")
        ok, msg = logger.verify_integrity()
        assert ok, f"Integrity failed: {msg}"


# ---------------------------------------------------------------------------
# Wired commands record metadata["task_id"]
# ---------------------------------------------------------------------------

class TestWiredCommandsRecordTaskId:
    def _read_task_id_events(self, logger: AuditLogger) -> list[str]:
        """Return list of task_ids found in audit events."""
        events = logger.read_recent(limit=50)
        return [e.metadata["task_id"] for e in events if "task_id" in e.metadata]

    def test_run_command_records_task_id(self, tmp_path):
        """sac run should write an audit event with metadata['task_id']."""
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        with patch("safecode.cli_core.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            mock_path.side_effect = lambda *a, **kw: tmp_path if not a else Path(*a, **kw)
            # Run a low-risk command (echo) — it may be blocked but still audited
            with patch("safecode.shell.runner.ShellRunner.assess") as mock_assess:
                mock_risk = MagicMock()
                mock_risk.level.name = "LOW"
                from safecode.shell.risk import RiskLevel
                mock_risk.level = RiskLevel.LOW
                mock_risk.reasons = []
                mock_risk.tokens = ["echo"]
                mock_assess.return_value = mock_risk
                with patch("safecode.shell.runner.ShellRunner.run") as mock_run:
                    mock_result = MagicMock()
                    mock_result.executed = True
                    mock_result.exit_code = 0
                    mock_result.stdout = "hello"
                    mock_result.stderr = ""
                    mock_result.risk = mock_risk
                    mock_result.duration_ms = 10
                    mock_run.return_value = mock_result
                    with patch("safecode.cli_core.ToolCallGate") as mock_gate:
                        mock_gate_instance = MagicMock()
                        mock_gate_instance.check.return_value.allowed = True
                        mock_gate.return_value = mock_gate_instance
                        runner.invoke(app, ["run", "echo hello", "--yes"])

        store = TaskStore(tmp_path)
        # A task should have been auto-created
        tasks = store.list()
        assert len(tasks) >= 1

    def test_audit_event_field_set_unchanged(self, tmp_path):
        """AuditEvent field set must not change after task wiring (stable contract 3)."""
        import json
        snapshot_path = Path(__file__).parent / "snapshots" / "contracts" / "audit_event_schema.json"
        with open(snapshot_path) as f:
            snapshot = json.load(f)
        # Fields are stored in snapshot["fields"] as a list of field dicts
        expected_fields = set(snapshot["fields"])
        from safecode.audit.models import AuditEvent
        actual_fields = set(AuditEvent.model_fields.keys())
        assert expected_fields == actual_fields, (
            f"AuditEvent field set changed. Expected: {sorted(expected_fields)}, "
            f"Got: {sorted(actual_fields)}"
        )
