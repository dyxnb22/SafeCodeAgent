"""sac fix command: run last failing test, propose a patch, leave it pending for sac apply."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
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
from safecode.shell.runner import ShellRunResult, ShellRunner
from safecode.task.wiring import (
    count_fix_proposals,
    get_or_create_current_task,
    record_fix_on_task,
    redacted_tail_hash,
)
from safecode.task.recovery import mark_task_interrupted

_DEFAULT_MAX_ITERATIONS = 3
_DEFAULT_TIMEOUT_SECONDS = 120
_VALID_RERUN_SUITES = frozenset({"test", "all"})
_SUITE_ORDER = ("test", "lint", "typecheck", "build")


@dataclass(frozen=True)
class FixCommandRun:
    command: str
    output: str
    exit_code: int
    suite: str = "test"
    skipped_suites: tuple[str, ...] = ()
    failure_category: str | None = None


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


def _run_single_test(project_root: Path, command: str, timeout_seconds: int) -> FixCommandRun:
    output, exit_code = _run_test_command(project_root, command, timeout_seconds=timeout_seconds)
    category = "command_timeout" if exit_code == 124 else None
    return FixCommandRun(command=command, output=output, exit_code=exit_code, suite="test", failure_category=category)


def _combined_shell_output(result: ShellRunResult) -> str:
    return ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()


def _run_profile_suites(project_root: Path, timeout_seconds: int) -> FixCommandRun:
    """Run profile suites in deterministic order through ShellRunner."""
    from safecode.project.profile import load_profile

    profile = load_profile(project_root)
    if profile is None:
        return FixCommandRun(
            command="",
            output="No project profile found. Run 'sac profile detect' first.",
            exit_code=1,
            suite="all",
            failure_category="missing_profile",
        )

    runner = ShellRunner(project_root)
    skipped: list[str] = []
    last_command = ""
    for suite in _SUITE_ORDER:
        suite_cmd = getattr(profile, suite)
        if suite_cmd is None:
            skipped.append(suite)
            continue
        command = " ".join(suite_cmd.command)
        last_command = command
        result = runner.run(command, approved=True, timeout_seconds=timeout_seconds)
        output = _combined_shell_output(result)
        category = "command_timeout" if result.exit_code == 124 else None
        if not result.executed and result.exit_code in {125, 126}:
            category = "blocked_suite_command"
        if result.exit_code != 0:
            return FixCommandRun(
                command=command,
                output=output,
                exit_code=result.exit_code,
                suite=suite,
                skipped_suites=tuple(skipped),
                failure_category=category,
            )

    note = ""
    if skipped:
        note = "Skipped missing profile suites: " + ", ".join(skipped)
    return FixCommandRun(
        command=last_command or "profile suites",
        output=note,
        exit_code=0,
        suite="all",
        skipped_suites=tuple(skipped),
    )


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
    failure_category: str | None = None,
    skipped_suites: tuple[str, ...] = (),
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
    if failure_category is not None:
        data["failure_category"] = failure_category
    if skipped_suites:
        data["skipped_suites"] = list(skipped_suites)
    print(render_json(CLIJSONResponse(command="fix", status=status, data=data, error=error)))


def run_fix(
    project_root: Path,
    *,
    json_output: bool = False,
    test_command: Optional[str] = None,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
) -> int:
    """Core fix logic. Returns exit code."""
    if timeout_seconds < 1:
        msg = "--timeout-seconds must be at least 1."
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

    # Wire task sidecar (experimental)
    try:
        current_task_for_fix = get_or_create_current_task(project_root, "fix")
    except Exception:
        current_task_for_fix = None
    fix_task_id = current_task_for_fix.task_id if current_task_for_fix else None

    if not json_output:
        console.print(f"[blue]Running test command:[/blue] {cmd}")

    # Step 2: run the test
    try:
        run = _run_single_test(project_root, cmd, timeout_seconds)
    except KeyboardInterrupt:
        mark_task_interrupted(project_root, command_name="fix", hint=cmd, task_id=fix_task_id)
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error="Interrupted. resume with: sac resume")))
        else:
            console.print("[yellow]Interrupted. resume with: sac resume[/yellow]")
        return 130
    raw_output, exit_code = run.output, run.exit_code

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
    if exit_code == 124:
        if fix_task_id:
            try:
                record_fix_on_task(
                    project_root,
                    fix_task_id,
                    cmd,
                    exit_code,
                    redacted_output,
                    mode="plain",
                    status="failed",
                    failure_category="command_timeout",
                )
            except Exception:
                pass
        msg = f"Test command timed out after {timeout_seconds} seconds."
        if json_output:
            print(render_json(CLIJSONResponse(
                command="fix",
                status="error",
                data={
                    "test_command": cmd,
                    "test_exit_code": exit_code,
                    "task_id": fix_task_id,
                    "failure_category": "command_timeout",
                },
                error=msg,
            )))
        else:
            console.print(f"[red]{msg}[/red]")
        return 124
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
    except KeyboardInterrupt:
        mark_task_interrupted(project_root, command_name="fix", hint=cmd, task_id=fix_task_id)
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error="Interrupted. resume with: sac resume")))
        else:
            console.print("[yellow]Interrupted. resume with: sac resume[/yellow]")
        return 130
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
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
) -> int:
    """Run one approval-gated fix-watch iteration."""
    if rerun_suite not in _VALID_RERUN_SUITES:
        msg = "Unsupported --rerun-suite value. Use: test or all."
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

    if timeout_seconds < 1:
        msg = "--timeout-seconds must be at least 1."
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        return 1

    if rerun_suite == "all":
        cmd = ""
        error = None
    else:
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
        label = "profile suites" if rerun_suite == "all" else cmd
        console.print(f"[blue]Running test command:[/blue] {label}")
    try:
        run = _run_profile_suites(project_root, timeout_seconds) if rerun_suite == "all" else _run_single_test(project_root, cmd, timeout_seconds)
    except KeyboardInterrupt:
        mark_task_interrupted(project_root, command_name="fix --watch", hint=cmd, task_id=task_id)
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error="Interrupted. resume with: sac resume")))
        else:
            console.print("[yellow]Interrupted. resume with: sac resume[/yellow]")
        return 130
    cmd = run.command or cmd
    raw_output, exit_code = run.output, run.exit_code
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
                skipped_suites=run.skipped_suites,
            )
        else:
            console.print(f"[green]{next_step}[/green]")
        return 0

    if run.failure_category == "command_timeout":
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
                    failure_category="command_timeout",
                )
            except Exception:
                pass
        msg = f"Test command timed out after {timeout_seconds} seconds."
        if json_output:
            _json_fix_watch(
                status="error",
                task_id=task_id,
                iteration_index=iteration_index,
                test_command=cmd,
                test_exit_code=exit_code,
                next_step="Run 'sac status' and inspect the timeout before retrying.",
                failure_category="command_timeout",
                skipped_suites=run.skipped_suites,
                error=msg,
            )
        else:
            console.print(f"[red]{msg}[/red]")
            console.print("[yellow]Next step: sac status[/yellow]")
        return 124

    if run.failure_category == "missing_profile":
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
                    failure_category="missing_profile",
                )
            except Exception:
                pass
        msg = "No project profile found. Run 'sac profile detect' first."
        if json_output:
            _json_fix_watch(
                status="error",
                task_id=task_id,
                iteration_index=iteration_index,
                test_command=cmd,
                test_exit_code=exit_code,
                next_step="Run 'sac profile detect' before using --rerun-suite all.",
                failure_category="missing_profile",
                error=msg,
            )
        else:
            console.print(f"[yellow]{msg}[/yellow]")
        return 1

    current_hash = redacted_tail_hash(redacted_output)
    previous_fix = None
    if task_state:
        previous_fix = next((i for i in reversed(task_state.iterations) if i.event == "fix" and i.tail_hash), None)
    if current_hash and previous_fix is not None and previous_fix.tail_hash == current_hash:
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
                    failure_category="loop_no_progress",
                )
            except Exception:
                pass
        msg = "No progress detected: two consecutive failing fix iterations have the same failure tail hash."
        next_step = "Run 'sac status' and inspect the task before retrying."
        if json_output:
            _json_fix_watch(
                status="error",
                task_id=task_id,
                iteration_index=iteration_index,
                test_command=cmd,
                test_exit_code=exit_code,
                next_step=next_step,
                failure_category="loop_no_progress",
                skipped_suites=run.skipped_suites,
                error=msg,
            )
        else:
            console.print(f"[red]{msg}[/red]")
            console.print(f"[yellow]Next step: {next_step}[/yellow]")
        return 1

    if run.failure_category == "blocked_suite_command":
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
                    suite=run.suite,
                    status="failed",
                    failure_category="blocked_suite_command",
                )
            except Exception:
                pass
        msg = "Suite command was blocked by SafeCode command policy."
        if json_output:
            _json_fix_watch(
                status="error",
                task_id=task_id,
                iteration_index=iteration_index,
                test_command=cmd,
                test_exit_code=exit_code,
                next_step="Run 'sac profile show' and inspect the blocked suite command.",
                failure_category="blocked_suite_command",
                skipped_suites=run.skipped_suites,
                error=msg,
            )
        else:
            console.print(f"[red]{msg}[/red]")
            console.print("[yellow]Next step: sac profile show[/yellow]")
        return exit_code

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
                    failure_category=None,
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
                skipped_suites=run.skipped_suites,
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
    except KeyboardInterrupt:
        mark_task_interrupted(project_root, command_name="fix --watch", hint=cmd, task_id=task_id)
        if json_output:
            print(render_json(CLIJSONResponse(command="fix", status="error", error="Interrupted. resume with: sac resume")))
        else:
            console.print("[yellow]Interrupted. resume with: sac resume[/yellow]")
        return 130
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
                suite=run.suite if rerun_suite == "all" else rerun_suite,
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
            skipped_suites=run.skipped_suites,
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
            help="[EXPERIMENTAL] Suite to rerun in watch mode: test|all.",
        ),
        timeout_seconds: int = typer.Option(
            _DEFAULT_TIMEOUT_SECONDS,
            "--timeout-seconds",
            help="[EXPERIMENTAL] Timeout for each test/suite command.",
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
                timeout_seconds=timeout_seconds,
            )
        else:
            code = run_fix(
                Path.cwd(),
                json_output=json_output,
                test_command=test_command,
                timeout_seconds=timeout_seconds,
            )
        raise typer.Exit(code=code)
