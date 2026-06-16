"""run_command native tool — passes through existing ShellRunner/policy stack (v4.21.1+).

Safety invariants:
- High-risk commands: blocked, returns status="blocked".
- cwd must be within the project root.
- Same risk classification and high-risk block rules as `sac run`.
- Never raises; all failure paths return NativeToolResult.

v5.1.1: full-auto-mode support via full_auto_delay_ms parameter.
In full-auto mode, a preview line is printed and execution is delayed
(default 500 ms). Ctrl-C during the delay aborts cleanly (status=blocked).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolResult, NativeToolSpec
from safecode.config import SafeCodeConfig
from safecode.hooks.runner import HookRunner, is_test_command
from safecode.shell.runner import ShellRunner


_DEFAULT_TIMEOUT = 60
_FULL_AUTO_PREVIEW_PREFIX = "  → run_command  "
_OUTPUT_COLLAPSE_LINES = 40
_OUTPUT_HEAD_TAIL = 5


def _collapse_output(text: str) -> str:
    """Collapse long command output: show first 5 + last 5 lines with a hidden-count line (v5.2.1)."""
    if not text:
        return text
    lines = text.splitlines()
    if len(lines) <= _OUTPUT_COLLAPSE_LINES:
        return text
    hidden = len(lines) - _OUTPUT_HEAD_TAIL * 2
    parts = (
        lines[:_OUTPUT_HEAD_TAIL]
        + [f"--- [{hidden} lines hidden] ---"]
        + lines[-_OUTPUT_HEAD_TAIL:]
    )
    return "\n".join(parts)


def _run_command_handler(call_id: str, inp: dict[str, Any]) -> NativeToolResult:
    project_root = Path(inp.get("_project_root", ".")).resolve()
    command: str = inp.get("command", "")
    raw_cwd: str = inp.get("cwd", "") or ""
    timeout: int = int(inp.get("timeout_seconds", _DEFAULT_TIMEOUT))
    full_auto_delay_ms: int = int(inp.get("_full_auto_delay_ms", -1))

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

    # Full-auto mode: print preview and sleep before executing.
    # Ctrl-C during the delay aborts the command cleanly.
    if full_auto_delay_ms >= 0:
        import sys
        print(f"{_FULL_AUTO_PREVIEW_PREFIX}{command}", file=sys.stdout, flush=True)
        if full_auto_delay_ms > 0:
            try:
                time.sleep(full_auto_delay_ms / 1000.0)
            except KeyboardInterrupt:
                return NativeToolResult(
                    call_id=call_id,
                    tool_name="run_command",
                    status="blocked",
                    error="Command aborted by Ctrl-C during full-auto delay.",
                    metadata={"command": command, "aborted": True},
                )

    start = time.monotonic()
    hook_runner = HookRunner(project_root, config)
    if runner.propose(command, approved=True).decision.allowed:
        hook_runner.run_before_command()
    result = runner.run(command, approved=True, timeout_seconds=timeout)
    if is_test_command(command):
        hook_runner.run_after_test()
    elapsed_ms = int((time.monotonic() - start) * 1000)

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

    # Full-auto: print exit code line after execution.
    if full_auto_delay_ms >= 0:
        import sys
        icon = "✓" if result.exit_code == 0 else "✗"
        duration_s = elapsed_ms / 1000
        print(f"  {icon} exit {result.exit_code} ({duration_s:.1f}s)", file=sys.stdout, flush=True)

    raw_output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    raw_output = raw_output.strip()
    # v5.2.1: collapse long output for model context (full output still in audit log)
    collapsed_output = _collapse_output(raw_output)
    return NativeToolResult(
        call_id=call_id,
        tool_name="run_command",
        status="success",
        output=collapsed_output,
        metadata={
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms if result.duration_ms is not None else elapsed_ms,
            "command": command,
            "output_collapsed": collapsed_output != raw_output,
            "full_output_lines": len(raw_output.splitlines()),
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


def register_command_tool(
    dispatcher: NativeToolDispatcher,
    project_root: Path,
    *,
    full_auto_delay_ms: int = -1,
) -> None:
    """Register run_command on a dispatcher, injecting project_root.

    full_auto_delay_ms >= 0: enable full-auto mode with a preview + delay
    before execution (default -1 = disabled). Zero means immediate execution
    with preview only (for CI/scripting).
    """

    def _handler(call_id: str, inp: dict) -> NativeToolResult:
        return _run_command_handler(call_id, {
            "_project_root": str(project_root),
            "_full_auto_delay_ms": full_auto_delay_ms,
            **inp,
        })

    dispatcher.register(RUN_COMMAND_SPEC, _handler)
