"""File-backed subagent tasks."""

import json
import re
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from safecode.utils.time import utc_now_iso

SAFE_TASK_ID_RE = re.compile(r"^[a-f0-9]{1,64}$")


def validate_task_id(task_id: str) -> str:
    """Reject task IDs that could escape the subagents directory."""
    if not SAFE_TASK_ID_RE.match(task_id):
        raise ValueError(f"Unsafe task ID: {task_id!r}. Must be hex characters only.")
    return task_id


class SubagentTask(BaseModel):
    """A scoped subagent task with lifecycle tracking."""

    id: str
    title: str
    instructions: str
    readonly: bool = True
    status: str = "pending"
    created_at: str = Field(default_factory=utc_now_iso)
    started_at: str | None = None
    completed_at: str | None = None
    result_path: str | None = None
    error: str | None = None


class SubagentTaskStore:
    """Persist subagent tasks and results under .sac/subagents."""

    def __init__(self, project_root: Path) -> None:
        self.root = project_root / ".sac" / "subagents"

    def create(self, title: str, instructions: str, readonly: bool = True) -> SubagentTask:
        """Create a new pending task file."""
        task = SubagentTask(
            id=uuid4().hex[:12],
            title=title,
            instructions=instructions,
            readonly=readonly,
        )
        self._write_task(task)
        return task

    def load(self, task_id: str) -> SubagentTask | None:
        """Load a task by ID."""
        validate_task_id(task_id)
        task_file = self.root / task_id / "task.json"
        if not task_file.exists():
            return None
        try:
            return SubagentTask(**json.loads(task_file.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def update_status(
        self,
        task: SubagentTask,
        status: str,
        result_path: str | None = None,
        error: str | None = None,
    ) -> SubagentTask:
        """Update task status and persist."""
        updated = task.model_copy(
            update={
                "status": status,
                "result_path": result_path,
                "error": error,
                "started_at": task.started_at or utc_now_iso() if status == "running" else task.started_at,
                "completed_at": utc_now_iso() if status in ("completed", "failed", "blocked") else task.completed_at,
            }
        )
        self._write_task(updated)
        return updated

    def list_tasks(self) -> list[SubagentTask]:
        """List all subagent tasks."""
        tasks: list[SubagentTask] = []
        if not self.root.exists():
            return tasks
        for task_dir in sorted(self.root.iterdir()):
            if not task_dir.is_dir():
                continue
            task_file = task_dir / "task.json"
            if not task_file.exists():
                continue
            try:
                tasks.append(SubagentTask(**json.loads(task_file.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return tasks

    def get_task(self, task_id: str) -> SubagentTask | None:
        """Alias for load, with validation."""
        return self.load(task_id)

    def result_exists(self, task_id: str) -> bool:
        """Check if a result file already exists for the task."""
        validate_task_id(task_id)
        return (self.root / task_id / "result.md").exists()

    def result_path_for(self, task_id: str) -> Path:
        """Return the expected result path for a task."""
        validate_task_id(task_id)
        return self.root / task_id / "result.md"

    def _write_task(self, task: SubagentTask) -> None:
        task_dir = self.root / task.id
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.json").write_text(
            json.dumps(task.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
