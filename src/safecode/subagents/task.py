"""File-backed subagent tasks."""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class SubagentTask:
    """A scoped subagent task."""

    id: str
    title: str
    instructions: str
    readonly: bool = True


class SubagentTaskStore:
    """Persist subagent tasks and results under .sac/subagents."""

    def __init__(self, project_root: Path) -> None:
        self.root = project_root / ".sac" / "subagents"

    def create(self, title: str, instructions: str, readonly: bool = True) -> SubagentTask:
        """Create a task file."""
        task = SubagentTask(id=uuid4().hex[:12], title=title, instructions=instructions, readonly=readonly)
        task_dir = self.root / task.id
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.json").write_text(json.dumps(asdict(task), indent=2), encoding="utf-8")
        return task

    def write_result(self, task: SubagentTask, result: str) -> Path:
        """Write a Markdown result file."""
        task_dir = self.root / task.id
        task_dir.mkdir(parents=True, exist_ok=True)
        path = task_dir / "result.md"
        path.write_text(result, encoding="utf-8")
        return path
