"""run_command native tool — passes through existing ShellRunner/policy stack (v4.21.1+).

Safety invariants:
- High-risk commands: blocked, returns status="blocked".
- cwd must be within the project root.
- Same risk classification and high-risk block rules as `sac run`.
- Never raises; all failure paths return NativeToolResult.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolResult, NativeToolSpec
from safecode.config import SafeCodeConfig
from safecode.shell.runner import ShellRunner


_DEFAULT_TIMEOUT = 60


def _run_command_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    command: str = inp.get("command", "")
    raw_cwd: str = inp.get("cwd", "") or ""
    timeout: int = int(inp.get("timeout_seconds", _DEFAULT_TIMEOUT))

    if not command:
        return NativeToolResult(call_id=call_id, tool_name="run_command", status="error",
                                error="Missing 'command' input.")

    # Validate cwd stays inside project root.
    if raw_cwd:
        candidate = Path(raw_cwd)
        absolute = candidate if candidate.is_absolute() else project_root / candidate
        try:
            absolute.resolve(strict=False).relative_to(project_root)
        except ValueError:
            return NativeToolResult(
                call_id=call_id, tool_name="run_command", status="blocked",
                error=f"cwd {raw_cwd!r} is outside the project root.",
            )

    config = SafeCodeConfig.load(project_root)
    runner = ShellRunner(project_root, config)

    result = runner.run(command, approved=True, timeout_seconds=timeout)

    if not result.executed:
        # Policy blocked or requires approval.
        status = "blocked"
        error = result.stderr or f"Command not executed: exit={result.exit_code}"
        return NativeToolResult(
            call_id=call_id,
            tool_name="run_command",
            status=status,
            error=error,
            metadata={"exit_code": result.exit_code, "risk": result.risk.level if hasattr(result.risk, 'level') else str(result.risk)},
        )

    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    return NativeToolResult(
        call_id=call_id,
        tool_name="run_command",
        status="success",
        output=output.strip(),
        metadata={
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "command": command,
        },
    )


RUN_COMMAND_SPEC = NativeToolSpec(
    name="run_command",
    description="Run a shell command via the existing ShellRunner/policy stack. High-risk commands are blocked.",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute."},
            "cwd": {"type": "string", "description": "Working directory (project-relative or absolute within project root)."},
            "timeout_seconds": {"type": "integer", "description": f"Execution timeout in seconds (default {_DEFAULT_TIMEOUT})."},
        },
        "required": ["command"],
    },
    requires_approval=False,
    audit_event_type="tool_call_command",
    experimental=False,  # Stable contract since v5.0.0
)


def register_command_tool(dispatcher: NativeToolDispatcher, project_root: Path) -> None:
    """Register run_command on a dispatcher, injecting project_root."""

    def _handler(call_id: str, inp: dict) -> NativeToolResult:
        return _run_command_handler(call_id, {"_project_root": str(project_root), **inp})

    dispatcher.register(RUN_COMMAND_SPEC, _handler)
