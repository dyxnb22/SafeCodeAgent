"""TaskStore: file-backed storage for task sidecars (experimental, v4.1+).

File layout under <project_root>/.sac/tasks/:
  <task_id>.json  — atomic JSON sidecar for one task
  INDEX           — sorted lines: <id>\t<status>\t<updated_at>\t<goal>
  CURRENT         — single line: current task_id (missing = no current task)

All writes are atomic via tmp + os.replace.
Refuses to overwrite a sidecar whose payload_version > 1 (fail closed).
Missing files never cause exceptions on read paths.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from safecode.task.state import TaskState, _SUPPORTED_PAYLOAD_VERSION
from safecode.utils.time import utc_now_iso

_TASK_DIR_NAME = "tasks"
_SLUG_MAX_LEN = 30
_HASH_LEN = 8


def _make_task_id(goal: str, timestamp: str) -> str:
    """Generate a short kebab-case task id from goal + timestamp."""
    slug_raw = re.sub(r"[^a-z0-9]+", "-", goal.lower().strip())[:_SLUG_MAX_LEN]
    slug = slug_raw.strip("-") or "task"
    short_hash = hashlib.sha256(f"{goal}\n{timestamp}".encode()).hexdigest()[:_HASH_LEN]
    task_id = f"{slug}-{short_hash}"
    return task_id[:39]


class TaskStore:
    """Manage task sidecar files for a project root (experimental)."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.tasks_dir = project_root / ".sac" / _TASK_DIR_NAME

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, goal: str) -> TaskState:
        """Create a new task sidecar and set CURRENT. Raises ValueError on empty goal."""
        if not goal or not goal.strip():
            raise ValueError("Task goal must be non-empty.")
        now = utc_now_iso()
        task_id = _make_task_id(goal.strip(), now)
        state = TaskState(
            task_id=task_id,
            goal=goal.strip(),
            created_at=now,
            updated_at=now,
        )
        self.save(state)
        self.set_current(task_id)
        return state

    def load(self, task_id: str) -> TaskState | None:
        """Load a task sidecar by id. Returns None if missing or unparseable."""
        path = self._task_path(task_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TaskState(**data)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return None

    def save(self, state: TaskState) -> None:
        """Atomically persist a task sidecar. Fails closed if payload_version > supported."""
        existing = self.load(state.task_id)
        if existing is not None and existing.payload_version > _SUPPORTED_PAYLOAD_VERSION:
            raise ValueError(
                f"Cannot overwrite task sidecar with payload_version={existing.payload_version} "
                f"(supported: {_SUPPORTED_PAYLOAD_VERSION}). Upgrade SafeCode Agent."
            )
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        path = self._task_path(state.task_id)
        updated = state.model_copy(update={"updated_at": utc_now_iso()})
        _atomic_write(path, updated.model_dump_json(indent=2))
        self._rewrite_index()

    def list(self) -> tuple[TaskState, ...]:
        """Return all tasks sorted by created_at descending (newest first)."""
        if not self.tasks_dir.exists():
            return ()
        states: list[TaskState] = []
        for path in self.tasks_dir.glob("*.json"):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                states.append(TaskState(**data))
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                continue
        states.sort(key=lambda s: s.created_at, reverse=True)
        return tuple(states)

    def current_id(self) -> str | None:
        """Return the current task id from CURRENT, or None if missing/empty."""
        current_path = self.tasks_dir / "CURRENT"
        if not current_path.exists():
            return None
        try:
            raw = current_path.read_text(encoding="utf-8").strip()
            return raw if raw else None
        except OSError:
            return None

    def set_current(self, task_id: str) -> None:
        """Write CURRENT to point to the given task id."""
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.tasks_dir / "CURRENT", task_id + "\n")

    def clear_current(self) -> None:
        """Clear the CURRENT pointer (write empty)."""
        if not self.tasks_dir.exists():
            return
        _atomic_write(self.tasks_dir / "CURRENT", "")

    def delete(self, task_id: str) -> bool:
        """Delete a task sidecar. Returns True if deleted, False if not found."""
        path = self._task_path(task_id)
        if not path.exists():
            return False
        path.unlink()
        current = self.current_id()
        if current == task_id:
            self.clear_current()
        self._rewrite_index()
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def _rewrite_index(self) -> None:
        """Rewrite INDEX from the current set of task sidecars (sorted by created_at)."""
        if not self.tasks_dir.exists():
            return
        states = self.list()
        lines = [
            f"{s.task_id}\t{s.status}\t{s.updated_at}\t{s.goal}\n"
            for s in states
        ]
        _atomic_write(self.tasks_dir / "INDEX", "".join(lines))


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via a sibling tmp file + os.replace."""
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
