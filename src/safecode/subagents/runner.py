"""Read-only subagent runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.context.collector import ContextCollector
from safecode.context.redactor import redact_secrets
from safecode.logs.runtime import RuntimeLogger
from safecode.sandbox.filesystem import FilesystemBoundary
from safecode.subagents.task import SubagentTask, SubagentTaskStore, validate_task_id
from safecode.utils.time import utc_now_iso


@dataclass(frozen=True)
class SubagentRunResult:
    """Outcome of a subagent run."""

    task: SubagentTask
    result_path: Path | None
    executed: bool
    error: str | None


class ReadonlySubagentRunner:
    """Run a subagent task in read-only mode, writing only a result file."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.store = SubagentTaskStore(project_root)
        self.audit_logger = AuditLogger(project_root, self.config)
        self.runtime_logger = RuntimeLogger(project_root, self.config)
        self.filesystem = FilesystemBoundary(project_root, self.config)

    def run(self, title: str, instructions: str) -> SubagentRunResult:
        """Create and run a new read-only subagent task."""
        task = self.store.create(title, instructions, readonly=True)
        self._audit("subagent_created", task, "Task created.")
        return self._execute(task)

    def run_existing(self, task_id: str) -> SubagentRunResult:
        """Run an existing subagent task by ID."""
        validate_task_id(task_id)
        task = self.store.load(task_id)
        if task is None:
            raise FileNotFoundError(f"Subagent task not found: {task_id}")
        if not task.readonly:
            self._audit("subagent_blocked", task, "Non-readonly tasks cannot be executed.")
            raise PermissionError("Only read-only subagent tasks can be executed.")
        return self._execute(task)

    def _execute(self, task: SubagentTask) -> SubagentRunResult:
        """Internal execution: validate, collect context, write result."""
        if not task.readonly:
            self._audit("subagent_blocked", task, "Non-readonly tasks are blocked.")
            return SubagentRunResult(task, None, False, "Non-readonly tasks are blocked.")

        if self.store.result_exists(task.id):
            self._audit("subagent_blocked", task, "Result file already exists.")
            raise FileExistsError(
                f"Result file already exists for task {task.id}. "
                "Each task can only be run once."
            )

        task = self.store.update_status(task, "running")
        self._audit("subagent_started", task, "Subagent started.")

        try:
            context = ContextCollector(self.project_root, self.config).collect()
            result_md = self._build_result(task, context)
            result_path = self._write_result(task, result_md)
        except Exception as exc:
            self.runtime_logger.error("subagent.runner", "Subagent execution failed", exc=exc)
            task = self.store.update_status(task, "failed", error=str(exc))
            self._audit("subagent_blocked", task, f"Subagent failed: {exc}")
            return SubagentRunResult(task, None, False, str(exc))

        task = self.store.update_status(task, "completed", result_path=str(result_path))
        self._audit("subagent_completed", task, f"Result written to {result_path}.")
        return SubagentRunResult(task, result_path, True, None)

    def _build_result(self, task: SubagentTask, context: dict) -> str:
        context_summary = self._summarize_context(context)
        redacted_summary = redact_secrets(context_summary)
        return (
            f"# Subagent Result\n\n"
            f"## Task\n\n"
            f"- **ID**: {task.id}\n"
            f"- **Title**: {task.title}\n"
            f"- **Readonly**: yes\n\n"
            f"## Instructions\n\n"
            f"{task.instructions}\n\n"
            f"## Context Summary\n\n"
            f"{redacted_summary}\n\n"
            f"## Write Status\n\n"
            f"No files were modified by this subagent. "
            f"This is a read-only execution. "
            f"Only this result file was written under `.sac/subagents/`.\n"
        )

    def _summarize_context(self, context: dict) -> str:
        files = context.get("files", [])
        file_list = ", ".join(files[:20])
        if len(files) > 20:
            file_list += f" ... ({len(files)} total)"
        parts = [f"Project files: {file_list}"]
        readme = context.get("readme")
        if readme:
            parts.append(f"README preview: {readme[:200]}")
        pyproject = context.get("pyproject")
        if pyproject:
            parts.append(f"pyproject.toml preview: {pyproject[:200]}")
        return "\n".join(parts)

    def _write_result(self, task: SubagentTask, content: str) -> Path:
        result_path = self.store.result_path_for(task.id)
        resolved = self.filesystem.validate(result_path)
        subagents_root = (self.project_root / self.config.sac_dir / "subagents").resolve()
        if not self._inside_directory(resolved, subagents_root):
            raise PermissionError("Subagent result path must stay under .sac/subagents.")
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(content, encoding="utf-8")
        return result_path

    def _inside_directory(self, path: Path, directory: Path) -> bool:
        try:
            path.resolve().relative_to(directory)
            return True
        except ValueError:
            return False

    def _audit(self, event_type: str, task: SubagentTask, message: str) -> None:
        self.audit_logger.write(
            AuditEvent(
                type=event_type,
                timestamp=utc_now_iso(),
                status="success" if "completed" in event_type or "created" in event_type or "started" in event_type else "blocked",
                message=message,
                metadata={
                    "task_id": task.id,
                    "title": task.title,
                    "readonly": str(task.readonly).lower(),
                },
            )
        )
