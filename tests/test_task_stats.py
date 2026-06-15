"""Tests for sac task stats (v4.19.0, EXPERIMENTAL)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.cli_task import task_app, _histogram
from safecode.task.budget import TaskBudgetStore, TaskBudget
from safecode.task.state import TaskIteration, TaskState, TaskCommand
from safecode.task.store import TaskStore

runner = CliRunner()


def _invoke(tmp_path: Path, *args: str):
    with patch("safecode.cli_task.Path") as mock_path:
        mock_path.cwd.return_value = tmp_path
        return runner.invoke(task_app, list(args), catch_exceptions=False)


def _store(tmp_path: Path) -> TaskStore:
    return TaskStore(tmp_path)


# ---------------------------------------------------------------------------
# Unit tests for _histogram helper
# ---------------------------------------------------------------------------


def test_histogram_empty():
    assert _histogram([]) == {}


def test_histogram_sorts_keys():
    result = _histogram(["b", "a", "b", "c"])
    assert list(result.keys()) == ["a", "b", "c"]
    assert result["b"] == 2


def test_histogram_skips_none():
    result = _histogram([None, "edit", None, "edit", "fix"])
    assert None not in result
    assert result == {"edit": 2, "fix": 1}


def test_histogram_none_not_skipped_when_flagged():
    result = _histogram([None, "edit"], skip_none=False)
    assert "None" in result
    assert result["edit"] == 1


# ---------------------------------------------------------------------------
# Integration tests via Typer CLI
# ---------------------------------------------------------------------------


def test_stats_no_current_task(tmp_path: Path):
    result = _invoke(tmp_path, "stats", "--json")
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["status"] == "error"
    assert "No task specified" in data["error"]


def test_stats_explicit_missing_task(tmp_path: Path):
    result = _invoke(tmp_path, "stats", "--task", "nonexistent-id", "--json")
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["status"] == "error"
    assert "Task not found" in data["error"]


def test_stats_zero_iterations(tmp_path: Path):
    store = _store(tmp_path)
    state = store.create("demo stats task")
    result = _invoke(tmp_path, "stats", "--task", state.task_id, "--json")
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "success"
    d = data["data"]
    assert d["iterations"]["total"] == 0
    assert d["iterations"]["last_iteration_index"] == -1
    assert d["iterations"]["last_event"] is None
    assert d["iterations"]["by_event"] == {}
    assert d["budget"]["steps"] == 8
    assert d["budget"]["time_seconds"] == 600
    assert d["experimental"] is True


def test_stats_mixed_event_iterations(tmp_path: Path):
    store = _store(tmp_path)
    state = store.create("mixed task")
    iters = [
        TaskIteration(iteration_index=0, event="edit", status="proposed"),
        TaskIteration(iteration_index=1, event="fix", status="failed"),
        TaskIteration(iteration_index=2, event="edit", status=None),
    ]
    store.save(state.model_copy(update={"iterations": iters}))
    result = _invoke(tmp_path, "stats", "--task", state.task_id, "--json")
    assert result.exit_code == 0
    d = json.loads(result.stdout)["data"]
    assert d["iterations"]["total"] == 3
    assert d["iterations"]["by_event"] == {"edit": 2, "fix": 1}
    assert d["iterations"]["by_status"] == {"failed": 1, "proposed": 1}  # None skipped


def test_stats_failure_category_none_skipped(tmp_path: Path):
    store = _store(tmp_path)
    state = store.create("fail task")
    iters = [
        TaskIteration(iteration_index=0, event="fix", failure_category=None),
        TaskIteration(iteration_index=1, event="fix", failure_category="budget_exceeded"),
        TaskIteration(iteration_index=2, event="fix", failure_category=None),
    ]
    store.save(state.model_copy(update={"iterations": iters}))
    result = _invoke(tmp_path, "stats", "--task", state.task_id, "--json")
    d = json.loads(result.stdout)["data"]
    assert d["iterations"]["by_failure_category"] == {"budget_exceeded": 1}


def test_stats_last_command_redacted(tmp_path: Path):
    store = _store(tmp_path)
    state = store.create("redact task")
    cmd = TaskCommand(command="curl https://api.example.com?api_key=supersecret", exit_code=0)
    store.save(state.model_copy(update={"last_command": cmd}))
    result = _invoke(tmp_path, "stats", "--task", state.task_id, "--json")
    d = json.loads(result.stdout)["data"]
    assert "supersecret" not in d["last_command"]["command"]


def test_stats_goal_redacted(tmp_path: Path):
    store = _store(tmp_path)
    state = store.create("fix API_KEY=abc123 endpoint")
    result = _invoke(tmp_path, "stats", "--task", state.task_id, "--json")
    d = json.loads(result.stdout)["data"]
    assert "abc123" not in d["goal"]


def test_stats_json_envelope(tmp_path: Path):
    store = _store(tmp_path)
    state = store.create("envelope check")
    result = _invoke(tmp_path, "stats", "--task", state.task_id, "--json")
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["command"] == "task stats"
    assert parsed["status"] == "success"
    assert "data" in parsed


def test_stats_pinned_files_count(tmp_path: Path):
    from safecode.memory.facade import MemoryFacade
    store = _store(tmp_path)
    state = store.create("pin test task")
    src = tmp_path / "myfile.py"
    src.write_text("x = 1")
    MemoryFacade(tmp_path).pin_file(src)
    result = _invoke(tmp_path, "stats", "--task", state.task_id, "--json")
    d = json.loads(result.stdout)["data"]
    assert d["pinned_files"]["count"] == 1


def test_stats_audit_trace_count(tmp_path: Path):
    store = _store(tmp_path)
    state = store.create("audit trace task")
    store.save(state.model_copy(update={"audit_trace_ids": ["t1", "t2", "t3"]}))
    result = _invoke(tmp_path, "stats", "--task", state.task_id, "--json")
    d = json.loads(result.stdout)["data"]
    assert d["audit_trace_count"] == 3


def test_stats_custom_budget(tmp_path: Path):
    store = _store(tmp_path)
    state = store.create("budget task")
    budget = TaskBudget(task_id=state.task_id, steps=5, time_seconds=300, retries=1, tokens=20000)
    TaskBudgetStore(tmp_path).save(budget)
    result = _invoke(tmp_path, "stats", "--task", state.task_id, "--json")
    d = json.loads(result.stdout)["data"]
    assert d["budget"] == {"steps": 5, "time_seconds": 300, "retries": 1, "tokens": 20000}


def test_stats_closed_task_readable(tmp_path: Path):
    store = _store(tmp_path)
    state = store.create("close me")
    store.save(state.model_copy(update={"status": "closed"}))
    result = _invoke(tmp_path, "stats", "--task", state.task_id, "--json")
    assert result.exit_code == 0
    d = json.loads(result.stdout)["data"]
    assert d["status"] == "closed"
