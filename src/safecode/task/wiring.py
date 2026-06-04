"""Task wiring helpers for CLI commands (experimental, v4.1+).

These helpers attach CLI commands (edit, apply, rollback, fix, run) to the current
task sidecar. If no CURRENT task is open, a new one is auto-created.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from safecode.task.state import TaskCommand, TaskIteration, TaskState
from safecode.task.store import TaskStore
from safecode.utils.time import utc_now_iso


def _auto_task_goal(command_name: str, hint: str) -> str:
    """Build an auto-task goal from the command name and a short hint."""
    prefix = f"auto: {command_name}"
    if hint:
        truncated = hint[:80].strip()
        return f"{prefix}: {truncated}"
    return prefix


def get_or_create_current_task(project_root: Path, command_name: str, hint: str = "") -> TaskState:
    """Return the CURRENT task, or auto-create one if none is open.

    Rules:
    - If CURRENT points to an open/interrupted/applied task: return it.
    - If CURRENT is missing, empty, not found, or points to a closed task: auto-create.
    """
    store = TaskStore(project_root)
    current_id = store.current_id()
    if current_id:
        state = store.load(current_id)
        if state is not None and state.status != "closed":
            return state
    # Auto-create
    goal = _auto_task_goal(command_name, hint)
    return store.create(goal)


def record_edit_on_task(project_root: Path, task_id: str, pending_patch_id: str) -> None:
    """Update the task sidecar when sac edit completes."""
    store = TaskStore(project_root)
    state = store.load(task_id)
    if state is None:
        return
    iteration = TaskIteration(
        iteration_index=state.next_iteration_index(),
        event="edit",
        pending_patch_id=pending_patch_id,
    )
    updated = state.model_copy(update={
        "pending_patch_id": pending_patch_id,
        "iterations": list(state.iterations) + [iteration],
    })
    store.save(updated)


def record_apply_on_task(project_root: Path, task_id: str, audit_trace_id: str) -> None:
    """Update the task sidecar when sac apply completes."""
    store = TaskStore(project_root)
    state = store.load(task_id)
    if state is None:
        return
    iteration = TaskIteration(
        iteration_index=state.next_iteration_index(),
        event="apply",
        audit_trace_id=audit_trace_id,
    )
    new_trace_ids = list(state.audit_trace_ids) + [audit_trace_id]
    updated = state.model_copy(update={
        "status": "applied",
        "pending_patch_id": None,
        "audit_trace_ids": new_trace_ids,
        "iterations": list(state.iterations) + [iteration],
    })
    store.save(updated)


def record_rollback_on_task(project_root: Path, task_id: str, audit_trace_id: str) -> None:
    """Update the task sidecar when sac rollback completes."""
    store = TaskStore(project_root)
    state = store.load(task_id)
    if state is None:
        return
    iteration = TaskIteration(
        iteration_index=state.next_iteration_index(),
        event="rollback",
        audit_trace_id=audit_trace_id,
    )
    new_trace_ids = list(state.audit_trace_ids) + [audit_trace_id]
    updated = state.model_copy(update={
        "status": "open",
        "audit_trace_ids": new_trace_ids,
        "iterations": list(state.iterations) + [iteration],
    })
    store.save(updated)


def record_fix_on_task(
    project_root: Path,
    task_id: str,
    test_command: str,
    test_exit_code: int,
    failure_output: str,
) -> None:
    """Update the task sidecar when sac fix runs a test."""
    store = TaskStore(project_root)
    state = store.load(task_id)
    if state is None:
        return
    tail_sha = hashlib.sha256(failure_output.encode("utf-8")).hexdigest() if failure_output else None
    iteration = TaskIteration(
        iteration_index=state.next_iteration_index(),
        event="fix",
        test_command=test_command,
        test_exit_code=test_exit_code,
        failure_tail_sha256=tail_sha,
    )
    updated = state.model_copy(update={
        "iterations": list(state.iterations) + [iteration],
    })
    store.save(updated)


def record_run_on_task(project_root: Path, task_id: str, command: str, exit_code: int) -> None:
    """Update the task sidecar when sac run executes a command."""
    store = TaskStore(project_root)
    state = store.load(task_id)
    if state is None:
        return
    last_cmd = TaskCommand(command=command, exit_code=exit_code)
    updated = state.model_copy(update={"last_command": last_cmd})
    store.save(updated)
