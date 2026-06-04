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
from safecode.task.wiring import count_fix_proposals, get_or_create_current_task, record_fix_on_task

_DEFAULT_MAX_ITERATIONS = 3
_DEFAULT_TIMEOUT_SECONDS = 120
_VALID_RERUN_SUITES = frozenset({"test"})


def _pending_patch_id(edit_result: object) -> str | None:
    proposal = getattr(edit_result, "proposal", None)
    proposal_id = getattr(proposal, "id", None)
    return str(proposal_id) if proposal_id else None


def _run_test_command(project_root: Path, command: str, timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS) -> tuple[str, int]:
    """Run a test command and return (combined_output, exit_code). Never raises on subprocess errors."""
    argv = command.split()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            cwd=str(project_root),
            shell=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return "Test command timed out.", 124
    except FileNotFoundError as exc:
        return f"Test command not found: {exc}", 127
    combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return combined.strip(), proc.returncode


def _select_test_command(project_root: Path, test_command: Optional[str] = None) -> tuple[str | None, str | None]:
    """Resolve the effective test command and return (command, error)."""
    from safecode.project.profile import load_profile

    if test_command:
        return test_command, None

    profile = load_profile(project_root)
    profile_cmd = profile.test if profile else None
    if profile_cmd is not None:
        return " ".join(profile_cmd.command), None

    detector = ProjectTestDetector(project_root)
    candidates = detector.detect()
    if not candidates:
        return None, "No test command detected in this project. Use --test-command to specify one."
    return candidates[0].command, None


def _failure_task_text(cmd: str, exit_code: int, redacted_output: str) -> str:
    return (
        f"Fix the failing test.\n"
        f"Test command: {cmd}\n"
        f"Exit code: {exit_code}\n\n"
        f"Failure output:\n{redacted_output}"
    )


def _json_fix_watch(
    *,
    status: str,
    task_id: str | None,
    iteration_index: int | None,
    test_command: str,
    test_exit_code: int,
    next_step: str,
    pending_patch_path: str | None = None,
    error: str | None = None,
) -> None:
    data = {
        "task_id": task_id,
        "iteration_index": iteration_index,
        "test_command": test_command,
        "test_exit_code": test_exit_code,
        "pending_patch_path": pending_patch_path,
        "next_step": next_step,
    }
    print(render_json(CLIJSONResponse(command="fix", status=status, data=data, error=error)))


def run_fix(
    project_root: Path,
    *,
    json_output: bool = False,
    test_command: Optional[str] = None,
) -> int:
    """Core fix logic. Returns exit code."""
    cmd, error = _select_test_command(project_root, test_command)
    if cmd is None:
        msg = error or "No test command detected."
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        return 1

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

    # Step 5: invoke AgentOrchestrator.edit() — leaves pending patch for user review
    try:
        edit_result = AgentOrchestrator(project_root).edit(fix_task_str)
    except (PatchParseError, PatchValidationError) as exc:
        if fix_task_id:
            try:
                record_fix_on_task(project_root, fix_task_id, cmd, exit_code, redacted_output, mode="plain", status="failed")
            except Exception:
                pass
        log_cli_error("cli.fix", "patch proposal failed", exc)
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error=str(exc))))
        else:
            console.print(f"[red]Patch proposal failed:[/red] {exc}")
        return 1
    except Exception as exc:
        if fix_task_id:
            try:
                record_fix_on_task(project_root, fix_task_id, cmd, exit_code, redacted_output, mode="plain", status="failed")
            except Exception:
                pass
        log_cli_error("cli.fix", "fix command failed", exc)
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error=str(exc))))
        else:
            console.print(f"[red]Fix failed:[/red] {exc}")
        return 1

    pending_patch_id = _pending_patch_id(edit_result)
    pending_patch_path = str(edit_result.pending_patch_path)
    if fix_task_id:
        try:
            record_fix_on_task(
                project_root,
                fix_task_id,
                cmd,
                exit_code,
                redacted_output,
                mode="plain",
                pending_patch_id=pending_patch_id,
                pending_patch_path=pending_patch_path,
                status="proposed",
            )
        except Exception:
            pass

    if json_output:
        print(render_json(CLIJSONResponse(
            command="fix",
            status="success",
            data={
                "pending_patch_path": pending_patch_path,
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


def run_fix_watch(
    project_root: Path,
    *,
    json_output: bool = False,
    test_command: Optional[str] = None,
    max_iterations: int = _DEFAULT_MAX_ITERATIONS,
    rerun_suite: str = "test",
) -> int:
    """Run one approval-gated fix-watch iteration."""
    if rerun_suite not in _VALID_RERUN_SUITES:
        msg = "Unsupported --rerun-suite value for v4.3.0. Use: test."
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        return 1
    if max_iterations < 1:
        msg = "--max-iterations must be at least 1."
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        return 1

    cmd, error = _select_test_command(project_root, test_command)
    if cmd is None:
        msg = error or "No test command detected."
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        return 1

    try:
        task_state = get_or_create_current_task(project_root, "fix --watch", cmd)
    except Exception:
        task_state = None
    task_id = task_state.task_id if task_state else None

    if not json_output:
        console.print(f"[blue]Running test command:[/blue] {cmd}")
    raw_output, exit_code = _run_test_command(project_root, cmd)
    redacted_output = redact_secrets(raw_output)

    if exit_code == 0:
        iteration_index = task_state.next_iteration_index() if task_state else None
        if task_id:
            try:
                record_fix_on_task(
                    project_root,
                    task_id,
                    cmd,
                    0,
                    "",
                    mode="watch",
                    suite=rerun_suite,
                    status="passed",
                )
            except Exception:
                pass
        next_step = "Tests passed. No pending patch was applied by sac fix --watch."
        if json_output:
            _json_fix_watch(
                status="success",
                task_id=task_id,
                iteration_index=iteration_index,
                test_command=cmd,
                test_exit_code=0,
                next_step=next_step,
            )
        else:
            console.print(f"[green]{next_step}[/green]")
        return 0

    proposals_used = count_fix_proposals(task_state) if task_state else 0
    if proposals_used >= max_iterations:
        iteration_index = task_state.next_iteration_index() if task_state else None
        if task_id:
            try:
                record_fix_on_task(
                    project_root,
                    task_id,
                    cmd,
                    exit_code,
                    redacted_output,
                    mode="watch",
                    suite=rerun_suite,
                    status="failed",
                )
            except Exception:
                pass
        msg = f"Max fix iterations reached ({max_iterations}). Inspect the failure before proposing another patch."
        if json_output:
            _json_fix_watch(
                status="error",
                task_id=task_id,
                iteration_index=iteration_index,
                test_command=cmd,
                test_exit_code=exit_code,
                next_step="Run 'sac status' and inspect the task sidecar before retrying.",
                error=msg,
            )
        else:
            console.print(f"[red]{msg}[/red]")
            console.print("[yellow]Next step: sac status[/yellow]")
        return 1

    if not json_output:
        console.print(f"[yellow]Test failed (exit {exit_code}). Proposing a pending patch...[/yellow]")

    try:
        edit_result = AgentOrchestrator(project_root).edit(_failure_task_text(cmd, exit_code, redacted_output))
    except (PatchParseError, PatchValidationError) as exc:
        log_cli_error("cli.fix", "patch proposal failed", exc)
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error=str(exc))))
        else:
            console.print(f"[red]Patch proposal failed:[/red] {exc}")
        return 1
    except Exception as exc:
        log_cli_error("cli.fix", "fix watch failed", exc)
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error=str(exc))))
        else:
            console.print(f"[red]Fix watch failed:[/red] {exc}")
        return 1

    pending_patch_path = str(edit_result.pending_patch_path)
    iteration_index = task_state.next_iteration_index() if task_state else None
    if task_id:
        try:
            record_fix_on_task(
                project_root,
                task_id,
                cmd,
                exit_code,
                redacted_output,
                mode="watch",
                suite=rerun_suite,
                pending_patch_id=_pending_patch_id(edit_result),
                pending_patch_path=pending_patch_path,
                status="proposed",
            )
        except Exception:
            pass

    next_step = "Review the pending patch, run 'sac apply', then run 'sac fix --watch' again."
    if json_output:
        _json_fix_watch(
            status="success",
            task_id=task_id,
            iteration_index=iteration_index,
            test_command=cmd,
            test_exit_code=exit_code,
            pending_patch_path=pending_patch_path,
            next_step=next_step,
        )
    else:
        console.print(f"[green]Pending patch saved:[/green] {pending_patch_path}")
        console.print(f"[yellow]Next step: {next_step}[/yellow]")
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
        watch: bool = typer.Option(False, "--watch", help="[EXPERIMENTAL] Run one approval-gated fix-watch iteration."),
        max_iterations: int = typer.Option(
            _DEFAULT_MAX_ITERATIONS,
            "--max-iterations",
            help="[EXPERIMENTAL] Maximum fix proposals recorded for the current task.",
        ),
        rerun_suite: str = typer.Option(
            "test",
            "--rerun-suite",
            help="[EXPERIMENTAL] Suite to rerun in watch mode (v4.3.0 supports: test).",
        ),
    ) -> None:
        """Run the last failing test, propose a repair patch, and leave it pending for sac apply."""
        if watch:
            code = run_fix_watch(
                Path.cwd(),
                json_output=json_output,
                test_command=test_command,
                max_iterations=max_iterations,
                rerun_suite=rerun_suite,
            )
        else:
            code = run_fix(Path.cwd(), json_output=json_output, test_command=test_command)
        raise typer.Exit(code=code)
