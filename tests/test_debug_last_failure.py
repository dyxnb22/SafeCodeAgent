"""Tests for experimental sac debug last-failure."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.cli import app
from safecode.cli_debug import find_last_failure
from safecode.logs.runtime import RuntimeLogger
from safecode.memory.facade import MemoryFacade
from safecode.task.state import TaskIteration
from safecode.task.store import TaskStore

runner = CliRunner()


def test_last_failure_from_runtime_log(tmp_path) -> None:
    RuntimeLogger(tmp_path).write(
        "error",
        "test",
        "command failed",
        failure_category="command_timeout",
        details={"command": "pytest -q", "task_id": "task-1"},
    )
    failure = find_last_failure(tmp_path)
    assert failure is not None
    assert failure.category == "command_timeout"
    assert failure.command == "pytest -q"
    assert failure.task_id == "task-1"
    assert failure.to_data()["suggested_next_command"]


def test_task_filter_selects_matching_task(tmp_path) -> None:
    store = TaskStore(tmp_path)
    first = store.create("first")
    store.save(first.model_copy(update={"iterations": [
        TaskIteration(iteration_index=0, event="fix", status="failed", failure_category="unknown")
    ]}))
    second = store.create("second")
    store.save(second.model_copy(update={"iterations": [
        TaskIteration(iteration_index=0, event="fix", status="failed", failure_category="loop_no_progress")
    ]}))
    failure = find_last_failure(tmp_path, task_id=first.task_id)
    assert failure is not None
    assert failure.task_id == first.task_id
    assert failure.category == "unknown"


def test_recent_failure_memory_is_redacted(tmp_path) -> None:
    MemoryFacade(tmp_path).record_failure(
        task_id="task-1",
        command="pytest -q",
        exit_code=1,
        tail="AssertionError password=hunter2",
    )
    failure = find_last_failure(tmp_path)
    assert failure is not None
    assert "hunter2" not in failure.message


def test_audit_event_candidate(tmp_path) -> None:
    AuditLogger(tmp_path).write(
        AuditEvent(
            type="shell_blocked",
            timestamp="2026-01-01T00:00:00+00:00",
            status="blocked",
            command="rm -rf /",
            exit_code=126,
            message="blocked by policy",
            metadata={"task_id": "task-1"},
        )
    )
    failure = find_last_failure(tmp_path)
    assert failure is not None
    assert failure.category == "command_blocked_by_policy"
    assert failure.command == "rm -rf /"


def test_cli_json_is_deterministic_and_redacted(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    RuntimeLogger(tmp_path).write(
        "error",
        "test",
        "token=s3cr3t",
        failure_category="provider_auth_failed",
        details={"command": "sac ask hi"},
    )
    result = runner.invoke(app, ["debug", "last-failure", "--json"], catch_exceptions=False)
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["command"] == "debug last-failure"
    assert data["status"] == "success"
    assert data["data"]["category"] == "provider_auth_failed"
    assert data["data"]["suggested_next_command"] == "sac setup --wizard"
    assert "s3cr3t" not in result.output
    assert result.output == runner.invoke(app, ["debug", "last-failure", "--json"], catch_exceptions=False).output


def test_cli_no_failure_found(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["debug", "last-failure", "--json"], catch_exceptions=False)
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["data"]["message"] == "No failure found."
    assert data["data"]["category"] is None


def test_last_failure_does_not_execute_commands(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    RuntimeLogger(tmp_path).write(
        "error",
        "test",
        "failed",
        failure_category="command_timeout",
        details={"command": "pytest -q"},
    )
    with patch("subprocess.run") as run:
        result = runner.invoke(app, ["debug", "last-failure", "--json"], catch_exceptions=False)
    assert result.exit_code == 0
    run.assert_not_called()
