"""Tests for task state sidecar (v4.1.0 T-4.1.0-A)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from safecode.task.state import TaskState, TaskIteration, TaskCommand, _SUPPORTED_PAYLOAD_VERSION
from safecode.task.store import TaskStore, _make_task_id


# ---------------------------------------------------------------------------
# TaskState model tests
# ---------------------------------------------------------------------------

class TestTaskStateModel:
    def test_defaults(self):
        state = TaskState(task_id="fix-auth-a1b2c3d4", goal="Fix auth bug")
        assert state.status == "open"
        assert state.payload_version == _SUPPORTED_PAYLOAD_VERSION
        assert state.pending_patch_id is None
        assert state.session_id is None
        assert state.audit_trace_ids == []
        assert state.iterations == []
        assert state.last_command is None

    def test_roundtrip_json(self, tmp_path):
        state = TaskState(
            task_id="my-task-abc12345",
            goal="Add /health endpoint",
            status="open",
        )
        raw = state.model_dump_json()
        loaded = TaskState(**json.loads(raw))
        assert loaded.task_id == state.task_id
        assert loaded.goal == state.goal
        assert loaded.payload_version == _SUPPORTED_PAYLOAD_VERSION

    def test_iteration_appended(self):
        state = TaskState(task_id="my-task-abc12345", goal="Test")
        assert state.next_iteration_index() == 0
        it = TaskIteration(iteration_index=0, event="edit", pending_patch_id="patch-001")
        updated = state.model_copy(update={"iterations": [it]})
        assert updated.next_iteration_index() == 1

    def test_task_command_model(self):
        cmd = TaskCommand(command="pytest tests/", exit_code=1)
        assert cmd.command == "pytest tests/"
        assert cmd.exit_code == 1
        assert cmd.timestamp  # auto-filled

    def test_status_values(self):
        for status in ("open", "applied", "interrupted", "closed"):
            s = TaskState(task_id="t-abc12345", goal="g", status=status)
            assert s.status == status

    def test_supported_payload_version(self):
        assert TaskState.supported_payload_version() == 1


# ---------------------------------------------------------------------------
# _make_task_id tests
# ---------------------------------------------------------------------------

class TestMakeTaskId:
    def test_kebab_case(self):
        tid = _make_task_id("Fix the auth bug!", "2026-01-01T00:00:00")
        assert "-" in tid
        assert tid == tid.lower()

    def test_short_enough(self):
        tid = _make_task_id("a" * 200, "ts")
        assert len(tid) <= 39

    def test_empty_goal_slug_fallback(self):
        tid = _make_task_id("!!!", "ts")
        assert tid.startswith("task-")

    def test_deterministic(self):
        t1 = _make_task_id("add /health route", "2026-01-01T00:00:00")
        t2 = _make_task_id("add /health route", "2026-01-01T00:00:00")
        assert t1 == t2

    def test_different_goals_different_ids(self):
        t1 = _make_task_id("fix auth", "2026-01-01T00:00:00")
        t2 = _make_task_id("add health", "2026-01-01T00:00:00")
        assert t1 != t2


# ---------------------------------------------------------------------------
# TaskStore tests
# ---------------------------------------------------------------------------

class TestTaskStore:
    def test_create_and_load(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("Fix the login flow")
        assert state.status == "open"
        assert state.goal == "Fix the login flow"
        loaded = store.load(state.task_id)
        assert loaded is not None
        assert loaded.task_id == state.task_id

    def test_create_empty_goal_raises(self, tmp_path):
        store = TaskStore(tmp_path)
        with pytest.raises(ValueError, match="non-empty"):
            store.create("")

    def test_create_sets_current(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("some task")
        assert store.current_id() == state.task_id

    def test_load_missing_returns_none(self, tmp_path):
        store = TaskStore(tmp_path)
        result = store.load("nonexistent-task-id")
        assert result is None

    def test_missing_tasks_dir_no_crash(self, tmp_path):
        store = TaskStore(tmp_path)
        assert store.list() == ()
        assert store.current_id() is None

    def test_atomic_write(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("atomic write test")
        tasks_dir = tmp_path / ".sac" / "tasks"
        task_file = tasks_dir / f"{state.task_id}.json"
        assert task_file.exists()
        # INDEX and CURRENT also exist
        assert (tasks_dir / "INDEX").exists()
        assert (tasks_dir / "CURRENT").exists()

    def test_current_pointer_roundtrip(self, tmp_path):
        store = TaskStore(tmp_path)
        s1 = store.create("task one")
        s2 = store.create("task two")
        assert store.current_id() == s2.task_id
        store.set_current(s1.task_id)
        assert store.current_id() == s1.task_id

    def test_clear_current(self, tmp_path):
        store = TaskStore(tmp_path)
        store.create("something")
        store.clear_current()
        assert store.current_id() is None

    def test_list_deterministic_order(self, tmp_path):
        store = TaskStore(tmp_path)
        s1 = store.create("first task")
        s2 = store.create("second task")
        s3 = store.create("third task")
        tasks = store.list()
        # Newest first (descending by created_at)
        assert tasks[0].task_id == s3.task_id
        assert tasks[-1].task_id == s1.task_id

    def test_list_consistent_multiple_calls(self, tmp_path):
        store = TaskStore(tmp_path)
        store.create("a task")
        store.create("b task")
        r1 = store.list()
        r2 = store.list()
        assert [s.task_id for s in r1] == [s.task_id for s in r2]

    def test_save_mutates_sidecar(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("task to mutate")
        updated = state.model_copy(update={"status": "closed"})
        store.save(updated)
        loaded = store.load(state.task_id)
        assert loaded is not None
        assert loaded.status == "closed"

    def test_payload_version_too_high_refused(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("test version guard")
        # Manually write a sidecar with payload_version=99
        path = tmp_path / ".sac" / "tasks" / f"{state.task_id}.json"
        data = json.loads(path.read_text())
        data["payload_version"] = 99
        path.write_text(json.dumps(data))
        # Attempt to save should be refused
        with pytest.raises(ValueError, match="payload_version"):
            store.save(state)

    def test_delete_task(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("delete me")
        assert store.load(state.task_id) is not None
        deleted = store.delete(state.task_id)
        assert deleted is True
        assert store.load(state.task_id) is None

    def test_delete_nonexistent_returns_false(self, tmp_path):
        store = TaskStore(tmp_path)
        assert store.delete("no-such-task-id") is False

    def test_delete_current_clears_current(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("to delete")
        assert store.current_id() == state.task_id
        store.delete(state.task_id)
        assert store.current_id() is None

    def test_index_file_content(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("index content test")
        index_path = tmp_path / ".sac" / "tasks" / "INDEX"
        content = index_path.read_text()
        assert state.task_id in content
        assert "open" in content
        assert state.goal in content

    def test_corrupted_sidecar_skipped_in_list(self, tmp_path):
        store = TaskStore(tmp_path)
        state = store.create("valid task")
        # Write a corrupted sidecar
        corrupt_path = tmp_path / ".sac" / "tasks" / "corrupt-task.json"
        corrupt_path.write_text("{not valid json}")
        tasks = store.list()
        task_ids = [s.task_id for s in tasks]
        assert state.task_id in task_ids
        assert "corrupt-task" not in task_ids
