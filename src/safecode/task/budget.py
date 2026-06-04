"""Per-task budget sidecars (experimental, v4.4+)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from safecode.task.state import TaskIteration
from safecode.task.store import TaskStore


DEFAULT_STEPS = 8
DEFAULT_TIME_SECONDS = 600
DEFAULT_RETRIES = 2
DEFAULT_TOKENS = 60_000


class TaskBudget(BaseModel):
    """Experimental per-task budget configuration."""

    task_id: str
    steps: int = DEFAULT_STEPS
    time_seconds: int = DEFAULT_TIME_SECONDS
    retries: int = DEFAULT_RETRIES
    tokens: int = DEFAULT_TOKENS
    payload_version: int = Field(default=1)

    @field_validator("steps", "time_seconds", "retries", "tokens")
    @classmethod
    def positive_int(cls, value: int) -> int:
        if not isinstance(value, int) or value < 1:
            raise ValueError("Budget values must be positive integers.")
        return value


class TaskBudgetStore:
    """File-backed budget sidecars linked to TaskStore task ids."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.root = project_root / ".sac" / "tasks" / "budgets"

    def load(self, task_id: str) -> TaskBudget:
        path = self._path(task_id)
        if not path.exists():
            return TaskBudget(task_id=task_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TaskBudget(**data)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return TaskBudget(task_id=task_id)

    def save(self, budget: TaskBudget) -> TaskBudget:
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write(self._path(budget.task_id), budget.model_dump_json(indent=2) + "\n")
        return budget

    def _path(self, task_id: str) -> Path:
        return self.root / f"{task_id}.json"


def resolve_budget_task(project_root: Path, task_id: str | None) -> tuple[str | None, str | None]:
    """Return (task_id, error) for explicit or CURRENT budget commands."""
    store = TaskStore(project_root)
    tid = task_id or store.current_id()
    if not tid:
        return None, "No task specified and no CURRENT task."
    state = store.load(tid)
    if state is None:
        return None, f"Task not found: {tid}"
    if state.status == "closed":
        return None, f"Task is closed: {tid}"
    return tid, None


def record_budget_exceeded(project_root: Path, task_id: str, budget_name: str) -> None:
    """Record an experimental budget_exceeded marker on the task sidecar."""
    store = TaskStore(project_root)
    state = store.load(task_id)
    if state is None:
        return
    iteration = TaskIteration(
        iteration_index=state.next_iteration_index(),
        event="budget",
        status="failed",
        failure_category="budget_exceeded",
        mode=budget_name,
    )
    store.save(state.model_copy(update={"iterations": list(state.iterations) + [iteration]}))


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
