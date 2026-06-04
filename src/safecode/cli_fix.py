"""sac fix command: run last failing test, propose a patch, leave it pending for sac apply."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import typer

from safecode.agent.orchestrator import AgentOrchestrator
from safecode.cli_shared import console, log_cli_error
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.context.redactor import redact_secrets
from safecode.patch.parser import PatchParseError
from safecode.patch.validator import PatchValidationError
from safecode.project.test_detector import ProjectTestDetector
from safecode.task.wiring import get_or_create_current_task, record_fix_on_task


def _run_test_command(project_root: Path, command: str) -> tuple[str, int]:
    """Run a test command and return (combined_output, exit_code). Never raises on subprocess errors."""
    argv = command.split()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            cwd=str(project_root),
            shell=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "Test command timed out.", 124
    except FileNotFoundError as exc:
        return f"Test command not found: {exc}", 127
    combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return combined.strip(), proc.returncode


def run_fix(
    project_root: Path,
    *,
    json_output: bool = False,
    test_command: Optional[str] = None,
) -> int:
    """Core fix logic. Returns exit code."""
    # Step 1: determine test command
    if test_command:
        cmd = test_command
    else:
        detector = ProjectTestDetector(project_root)
        candidates = detector.detect()
        if not candidates:
            msg = "No test command detected in this project. Use --test-command to specify one."
            if json_output:
                print(render_json(CLIJSONResponse(command="fix", status="error", error=msg)))
            else:
                console.print(f"[red]{msg}[/red]")
            return 1
        cmd = candidates[0].command

    # Wire task sidecar (experimental)
    try:
        current_task_for_fix = get_or_create_current_task(project_root, "fix")
    except Exception:
        current_task_for_fix = None
    fix_task_id = current_task_for_fix.task_id if current_task_for_fix else None

    if not json_output:
        console.print(f"[blue]Running test command:[/blue] {cmd}")

    # Step 2: run the test
    raw_output, exit_code = _run_test_command(project_root, cmd)

    if exit_code == 0:
        msg = "Tests are already passing — nothing to fix."
        if json_output:
            print(render_json(CLIJSONResponse(
                command="fix", status="success",
                data={"message": msg, "test_command": cmd, "test_exit_code": 0},
            )))
        else:
            console.print(f"[green]{msg}[/green]")
        return 0

    # Step 3 & 4: redact failure context
    redacted_output = redact_secrets(raw_output)
    fix_task_str = (
        f"Fix the failing test.\n"
        f"Test command: {cmd}\n"
        f"Exit code: {exit_code}\n\n"
        f"Failure output:\n{redacted_output}"
    )

    if not json_output:
        console.print(f"[yellow]Test failed (exit {exit_code}). Proposing a fix...[/yellow]")

    # Record the fix iteration in the task sidecar (experimental)
    if fix_task_id:
        try:
            record_fix_on_task(project_root, fix_task_id, cmd, exit_code, redacted_output)
        except Exception:
            pass

    # Step 5: invoke AgentOrchestrator.edit() — leaves pending patch for user review
    try:
        edit_result = AgentOrchestrator(project_root).edit(fix_task_str)
    except (PatchParseError, PatchValidationError) as exc:
        log_cli_error("cli.fix", "patch proposal failed", exc)
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error=str(exc))))
        else:
            console.print(f"[red]Patch proposal failed:[/red] {exc}")
        return 1
    except Exception as exc:
        log_cli_error("cli.fix", "fix command failed", exc)
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error=str(exc))))
        else:
            console.print(f"[red]Fix failed:[/red] {exc}")
        return 1

    if json_output:
        print(render_json(CLIJSONResponse(
            command="fix",
            status="success",
            data={
                "pending_patch_path": str(edit_result.pending_patch_path),
                "diff_text": edit_result.diff_text,
                "test_command": cmd,
                "test_exit_code": exit_code,
                "task_id": fix_task_id,
            },
        )))
    else:
        console.print(f"[green]Pending patch saved:[/green] {edit_result.pending_patch_path}")
        console.print("[yellow]Review the diff above, then run 'sac apply' to apply.[/yellow]")

    return 0


def register(app: typer.Typer) -> None:
    """Register the fix command on the given Typer app."""

    @app.command("fix")
    def fix_command(
        test_command: Optional[str] = typer.Option(
            None, "--test-command", "-t",
            help="Override the test command to run (default: auto-detect).",
        ),
        json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    ) -> None:
        """Run the last failing test, propose a repair patch, and leave it pending for sac apply."""
        code = run_fix(Path.cwd(), json_output=json_output, test_command=test_command)
        raise typer.Exit(code=code)
