"""A tiny file-backed task queue for v1.1 experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class QueueTask:
    """One queued local task."""

    id: str
    title: str
    status: str = "pending"


class QueueStore:
    """Persist queued tasks in .sac/queue.json."""

    def __init__(self, project_root: Path) -> None:
        self.path = project_root / ".sac" / "queue.json"

    def list(self) -> list[QueueTask]:
        """List tasks."""
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [QueueTask(**item) for item in data]

    def add(self, title: str) -> QueueTask:
        """Add a pending task."""
        tasks = self.list()
        task = QueueTask(id=uuid4().hex[:12], title=title)
        tasks.append(task)
        self._write(tasks)
        return task

    def complete_next(self) -> QueueTask | None:
        """Mark the first pending task completed."""
        tasks = self.list()
        updated: list[QueueTask] = []
        completed: QueueTask | None = None
        for task in tasks:
            if completed is None and task.status == "pending":
                completed = QueueTask(id=task.id, title=task.title, status="completed")
                updated.append(completed)
            else:
                updated.append(task)
        self._write(updated)
        return completed

    def _write(self, tasks: list[QueueTask]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([asdict(task) for task in tasks], indent=2, ensure_ascii=False), encoding="utf-8")
