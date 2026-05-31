"""Subagent dispatch executor for the agent loop (v2.2.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from safecode.config import SafeCodeConfig
from safecode.subagents.runner import ReadonlySubagentRunner
from safecode.subagents.task import SubagentTaskStore, validate_task_id
from safecode.tools.adapter import AdapterError, ToolCallAdapter


@dataclass(frozen=True)
class SubagentRequest:
    """A bounded subagent investigation request."""

    task: str
    scope: str
    max_steps: int


@dataclass(frozen=True)
class SubagentResult:
    """Structured outcome of a dispatched subagent investigation."""

    task_id: str
    summary: str
    observations: list[str] = field(default_factory=list)
    files_inspected: list[str] = field(default_factory=list)
    commands_attempted: list[str] = field(default_factory=list)
    blocked_actions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    success: bool = False
    blocked: bool = False


_MAX_STEPS_UPPER = 10
_MAX_STEPS_LOWER = 1


class SubagentDispatchExecutor:
    """Dispatch a read-only investigation subagent and return structured findings.

    All calls are validated through ToolCallAdapter before execution.
    Write attempts are blocked at multiple layers:
      - ReadonlySubagentRunner enforces readonly=True and confines writes to .sac/subagents/.
      - FilesystemBoundary in the runner blocks paths outside the project root.
      - No MCP write tools or shell commands are executed.
    Never raises — all failure paths return a blocked SubagentResult.
    """

    def __init__(
        self,
        project_root: Path,
        config: SafeCodeConfig | None = None,
        runner: ReadonlySubagentRunner | None = None,
    ) -> None:
        self.project_root = project_root
        self._config = config
        self._runner = runner
        self._adapter = ToolCallAdapter()

    def execute(self, task: Any, scope: Any, max_steps: Any) -> SubagentResult:
        """Validate and run a bounded read-only subagent investigation.

        Accepts Any for all three args so the loop can pass unvalidated model output
        directly here; ToolCallAdapter is the authoritative type gate.
        Validates args through ToolCallAdapter, enforces max_steps bounds,
        runs the investigation, and returns structured findings.
        Never raises.
        """
        try:
            self._adapter.validate(
                "subagent.dispatch",
                {"task": task, "scope": scope, "max_steps": max_steps},
            )
        except AdapterError as exc:
            return self._fail("", f"Adapter validation failed: {exc}")

        if not isinstance(max_steps, int) or max_steps < _MAX_STEPS_LOWER or max_steps > _MAX_STEPS_UPPER:
            return self._fail(
                "",
                f"max_steps must be between {_MAX_STEPS_LOWER} and {_MAX_STEPS_UPPER}, got {max_steps}",
            )

        if not task or not task.strip():
            return self._fail("", "task must be a non-empty string")

        instructions = f"Scope: {scope}\nTask: {task}"

        try:
            runner = self._runner or ReadonlySubagentRunner(self.project_root, self._config)
            run_result = runner.run(task.strip(), instructions)
        except Exception as exc:
            return self._fail("", f"Subagent run failed: {exc}")

        task_id = run_result.task.id

        if not run_result.executed or run_result.error:
            error_msg = run_result.error or "Subagent execution failed."
            return SubagentResult(
                task_id=task_id,
                summary=error_msg,
                observations=[],
                files_inspected=[],
                commands_attempted=[],
                blocked_actions=[f"Execution blocked: {error_msg}"],
                errors=[error_msg],
                success=False,
                blocked=True,
            )

        summary = ""
        files_inspected: list[str] = []
        observations: list[str] = []

        if run_result.result_path and run_result.result_path.exists():
            try:
                content = run_result.result_path.read_text(encoding="utf-8")
                summary = _extract_summary(content)
                files_inspected = _extract_files(content)
                if summary:
                    observations.append(summary)
            except Exception as exc:
                return self._fail(task_id, f"Failed to read subagent result: {exc}")

        return SubagentResult(
            task_id=task_id,
            summary=summary or f"Subagent completed task: {task}",
            observations=observations,
            files_inspected=files_inspected,
            commands_attempted=[],
            blocked_actions=[],
            errors=[],
            success=True,
            blocked=False,
        )

    def _fail(self, task_id: str, reason: str) -> SubagentResult:
        return SubagentResult(
            task_id=task_id,
            summary=reason,
            observations=[],
            files_inspected=[],
            commands_attempted=[],
            blocked_actions=[reason],
            errors=[reason],
            success=False,
            blocked=True,
        )


def _extract_summary(content: str) -> str:
    """Extract the context summary section from a subagent result file."""
    lines = content.splitlines()
    in_section = False
    summary_lines: list[str] = []
    for line in lines:
        if line.strip().startswith("## Context Summary"):
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            summary_lines.append(line)
    return "\n".join(summary_lines).strip()


def _extract_files(content: str) -> list[str]:
    """Extract file paths mentioned in the context summary."""
    files: list[str] = []
    for line in content.splitlines():
        if line.startswith("Project files:"):
            raw = line.removeprefix("Project files:").strip()
            # Strip trailing count annotation like "... (N total)"
            if "..." in raw:
                raw = raw[: raw.index("...")].strip()
            files = [f.strip() for f in raw.split(",") if f.strip()]
            break
    return files
