import json
import shlex
from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel
from rich.table import Table

from safecode.agent.loop import AgentLoop
from safecode.agent.loop_types import AgentRunResult
from safecode.agent.session import AgentSessionStore
from safecode.cli_shared import console
from safecode.state.journal import AgentJournalStore

agent_app = typer.Typer(help="Run and inspect interactive SafeCode agent sessions.")


@agent_app.command("start")
def agent_start(goal: str) -> None:
    """Start or replace the current interactive agent session."""
    store = AgentSessionStore(Path.cwd())
    state = store.start(goal)
    console.print(
        Panel.fit(
            f"Session ID: {state.session_id}\n"
            f"Goal: {state.goal}\n"
            f"Status: {state.status}\n"
            f"Session path: {store.path}",
            title="SafeCode Agent Session",
        )
    )


@agent_app.command("status")
def agent_status() -> None:
    """Show the current interactive agent session state."""
    store = AgentSessionStore(Path.cwd())
    state = store.load()
    if state is None:
        console.print("[yellow]No agent session found.[/yellow]")
        console.print("[yellow]Run 'sac agent start \"goal\"' first.[/yellow]")
        return

    table = Table(title="SafeCode Agent Session")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Session ID", state.session_id)
    table.add_row("Goal", state.goal)
    table.add_row("Status", state.status)
    table.add_row("Current Step", str(state.current_step))
    table.add_row("Plan Items", str(len(state.plan)))
    table.add_row(
        "Pending Action",
        json.dumps(state.pending_action, ensure_ascii=False) if state.pending_action else "(none)",
    )
    table.add_row("Last Observation", state.last_observation or "(none)")
    table.add_row("Last Error", state.last_error or "(none)")
    table.add_row("Created At", state.created_at)
    table.add_row("Updated At", state.updated_at)
    console.print(table)


@agent_app.command("clear")
def agent_clear() -> None:
    """Clear the current interactive agent session."""
    removed = AgentSessionStore(Path.cwd()).clear()
    if removed:
        console.print("[green]Agent session cleared.[/green]")
    else:
        console.print("[yellow]No agent session found.[/yellow]")


@agent_app.command("abort")
def agent_abort(reason: str = typer.Option("aborted by user", "--reason")) -> None:
    """Mark the current interactive agent session as aborted."""
    try:
        state = AgentSessionStore(Path.cwd()).abort(reason)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(Panel.fit(f"Session ID: {state.session_id}\nStatus: {state.status}\nReason: {state.last_error}", title="Agent Session Aborted"))


@agent_app.command("resume")
def agent_resume(
    session_id: str = typer.Argument("", help="Session ID to resume. Defaults to current session."),
) -> None:
    """Resume an existing non-completed interactive agent session."""
    store = AgentSessionStore(Path.cwd())
    if session_id:
        state = store.load_by_id(session_id)
        if state is None:
            console.print(f"[red]Session '{session_id}' not found or does not match the current session.[/red]")
            raise typer.Exit(code=1)
        if state.status == "contract_failed":
            console.print(f"[red]Session '{session_id}' has a contract failure and cannot be resumed.[/red]")
            raise typer.Exit(code=1)
    try:
        state = store.resume()
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(Panel.fit(f"Session ID: {state.session_id}\nStatus: {state.status}", title="Agent Session Resumed"))


@agent_app.command("explain-last-failure")
def agent_explain_last_failure() -> None:
    """Explain the latest recorded agent session failure."""
    try:
        explanation = AgentSessionStore(Path.cwd()).explain_last_failure()
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(Panel.fit(explanation, title="Agent Last Failure"))


@agent_app.command("journal")
def agent_journal(session_id: str = typer.Argument("", help="Session ID to render. Defaults to current session.")) -> None:
    """Render the current interactive agent session journal."""
    project_root = Path.cwd()
    store = AgentSessionStore(project_root)
    journal = AgentJournalStore(project_root)
    selected_session_id = session_id
    if not selected_session_id:
        state = store.load()
        selected_session_id = state.session_id if state else journal.latest_session_id() or ""
    if not selected_session_id:
        console.print("[yellow]No agent journal found.[/yellow]")
        return
    try:
        console.print(journal.render_markdown(selected_session_id))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


@agent_app.command("step")
def agent_step(goal: str = typer.Argument("", help="Goal to start or replace the session with.")) -> None:
    """Advance exactly one safe interactive agent step."""
    try:
        result = AgentLoop(Path.cwd()).step(goal or None)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Session ID: {result.state.session_id}\n"
            f"Goal: {result.state.goal}\n"
            f"Status: {result.state.status}\n"
            f"Current Step: {result.state.current_step}/{len(result.state.plan)}\n"
            f"Observation: {result.observation}",
            title="SafeCode Agent Step",
        )
    )


@agent_app.command("run")
def agent_run(
    goal: str = typer.Argument("", help="Goal to start or replace the session with."),
    max_steps: int = typer.Option(8, "--max-steps", min=1, help="Maximum steps to advance (default 8)."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    model: str = typer.Option("", "--model", help="One-shot model override (e.g. flash or deepseek:pro)."),
    auto_edit: bool = typer.Option(
        False,
        "--auto-edit",
        help="[EXPERIMENTAL] Auto-apply AUTO-tier edits. Approval gates still apply.",
    ),
    full_auto: bool = typer.Option(
        False,
        "--full-auto",
        help="[EXPERIMENTAL] Auto-apply AUTO and CONFIRM tiers. GATE-tier always stops.",
    ),
    run_tests: bool = typer.Option(
        False,
        "--tests",
        help="[EXPERIMENTAL] Run one detected project test command after the agent run.",
    ),
    auto_approve_read_only: bool = typer.Option(
        False,
        "--auto-approve-read-only",
        help="[EXPERIMENTAL] Auto-approve read-only ask steps. Never approves edit/apply/run/fix/commit/rollback.",
    ),
    no_validate: bool = typer.Option(
        False,
        "--no-validate",
        help="[EXPERIMENTAL] Skip validation loop. Logs a RuntimeWarning.",
    ),
) -> None:
    """[EXPERIMENTAL] Advance a bounded interactive agent loop."""
    import sys
    import warnings
    from safecode.cli_shared_json import CLIJSONResponse, render_json
    from safecode.agent.step_model import APPROVAL_REQUIRED_KINDS

    if model:
        from safecode.cli_model import apply_model_override_env
        try:
            apply_model_override_env(model)
        except ValueError as exc:
            if json_output:
                print(render_json(CLIJSONResponse(command="agent run", status="error", error=str(exc))))
            else:
                console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

    if no_validate:
        warnings.warn(
            "sac agent run --no-validate: validation loop disabled for this invocation.",
            RuntimeWarning,
            stacklevel=1,
        )

    is_tty = sys.stdin.isatty() and sys.stdout.isatty()

    step_updates: list[str] = []

    def on_step(result):
        obs = result.observation[:120]
        step_updates.append(obs)

    project_root = Path.cwd()
    try:
        loop = AgentLoop(project_root, auto_edit=auto_edit, full_auto=full_auto)
    except TypeError:
        # Older tests monkeypatch AgentLoop with minimal fakes that predate
        # trust-mode constructor flags. Runtime AgentLoop supports the flags.
        loop = AgentLoop(project_root)
    try:
        loop.no_validate = no_validate
    except Exception:
        pass
    try:
        if is_tty and not json_output and max_steps > 1:
            from rich.status import Status
            with Status("[bold blue]Agent loop running...", spinner="dots") as status:
                result = loop.run(goal or None, max_steps=max_steps, on_step=on_step)
        else:
            result = loop.run(goal or None, max_steps=max_steps, on_step=on_step)
    except KeyboardInterrupt:
        if json_output:
            print(render_json(CLIJSONResponse(command="agent run", status="error", error="Interrupted.")))
        else:
            console.print("[yellow]Agent loop interrupted.[/yellow]")
        raise typer.Exit(code=130)
    except (FileNotFoundError, ValueError) as exc:
        if json_output:
            print(render_json(CLIJSONResponse(command="agent run", status="error", error=str(exc))))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    # Non-TTY fail-closed: refuse approval-required steps that need mutation.
    if not is_tty and result.stopped_reason == "approval_required":
        last_typed = loop.last_typed_result
        if last_typed is not None and last_typed.kind in APPROVAL_REQUIRED_KINDS:
            msg = (
                f"Non-TTY mode: approval required for '{last_typed.kind}' step but no TTY available. "
                "Run interactively or approve the step manually."
            )
            if json_output:
                print(render_json(CLIJSONResponse(
                    command="agent run",
                    status="error",
                    error=msg,
                    data={
                        "session_id": result.state.session_id,
                        "stopped_reason": result.stopped_reason,
                        "steps_count": len(result.steps),
                        "status": result.state.status,
                    },
                )))
            else:
                console.print(f"[red]{msg}[/red]")
            raise typer.Exit(code=1)

    # --auto-approve-read-only: only allow ask/read-only kinds; block mutating kinds.
    if auto_approve_read_only and result.stopped_reason == "approval_required":
        last_typed = loop.last_typed_result
        if last_typed is not None and last_typed.kind in APPROVAL_REQUIRED_KINDS:
            msg = (
                f"--auto-approve-read-only cannot approve '{last_typed.kind}' step "
                "(only read-only 'ask' steps may be auto-approved)."
            )
            if json_output:
                print(render_json(CLIJSONResponse(
                    command="agent run",
                    status="error",
                    error=msg,
                    data={
                        "session_id": result.state.session_id,
                        "stopped_reason": result.stopped_reason,
                        "steps_count": len(result.steps),
                        "status": result.state.status,
                    },
                )))
            else:
                console.print(f"[red]{msg}[/red]")
            raise typer.Exit(code=1)

    validation = _run_agent_tests(project_root, result, enabled=run_tests)
    summary = _build_agent_run_summary(project_root, result, loop, validation)

    if json_output:
        status = result.stopped_reason if result.stopped_reason in ("completed", "approval_required") else "stopped"
        data: dict = {
            "session_id": result.state.session_id,
            "stopped_reason": result.stopped_reason,
            "steps_count": len(result.steps),
            "status": result.state.status,
            "tools_used": summary["tools_used"],
            "files_changed": summary["files_changed"],
            "validation": validation,
            "rollback_command": summary["rollback_command"],
        }
        last_typed = loop.last_typed_result
        if last_typed is not None:
            data["last_typed_result"] = last_typed.model_dump()
        print(render_json(CLIJSONResponse(
            command="agent run",
            status=status,
            data=data,
        )))
        return

    table = Table(title="SafeCode Agent Run")
    table.add_column("Step")
    table.add_column("Observation")
    for index, step in enumerate(result.steps, start=1):
        table.add_row(str(index), step.observation)
    console.print(table)
    console.print(
        Panel.fit(
            f"Session ID: {result.state.session_id}\n"
            f"Status: {result.state.status}\n"
            f"Current Step: {result.state.current_step}/{len(result.state.plan)}\n"
            f"Stopped Reason: {result.stopped_reason}\n"
            f"Tools: {', '.join(summary['tools_used']) or '(none)'}\n"
            f"Changed: {', '.join(summary['files_changed']) or '(none)'}\n"
            f"Validation: {_format_validation_line(validation)}\n"
            f"Rollback: {summary['rollback_command']}",
            title="Agent Run Summary",
        )
    )
    if result.stopped_reason == "approval_required":
        pending = result.state.pending_action or {}
        if pending.get("type") == "patch" and "pending_patch_path" in pending:
            patch_path = pending["pending_patch_path"]
            patch_id = pending.get("patch_id", "(unknown)")
            files = pending.get("files", [])
            files_line = ", ".join(files) if isinstance(files, list) else str(files)
            console.print(
                Panel.fit(
                    f"[bold]Patch proposal saved — no files modified yet.[/bold]\n"
                    f"File  : {patch_path}\n"
                    f"ID    : {patch_id}\n"
                    f"Target: {files_line}\n\n"
                    "[bold]Next steps:[/bold]\n"
                    "  sac apply          — preview diff and apply\n"
                    "  sac apply --preview — preview diff only",
                    title="[bold yellow]Approval Required — Pending Patch[/bold yellow]",
                    border_style="yellow",
                )
            )


def _run_agent_tests(
    project_root: Path,
    result: AgentRunResult,
    *,
    enabled: bool,
) -> dict[str, Any]:
    """Run a single detected test command for ``sac agent run --tests``.

    The command is executed through ``ShellRunner`` with an explicit approval
    because test commands are user-requested by the CLI flag. Mutating approval
    semantics for the agent itself are unchanged.
    """
    if not enabled:
        return {"requested": False, "status": "not_requested", "commands": []}
    if result.stopped_reason != "completed":
        return {
            "requested": True,
            "status": "skipped",
            "reason": f"agent_stopped_{result.stopped_reason}",
            "commands": [],
        }

    from safecode.project.test_detector import ProjectTestDetector
    from safecode.shell.runner import ShellRunner

    candidates = ProjectTestDetector(project_root).detect()
    test_candidates = [candidate for candidate in candidates if "test" in candidate.command.split()]
    selected = test_candidates[0] if test_candidates else (candidates[0] if candidates else None)
    if selected is None:
        return {
            "requested": True,
            "status": "skipped",
            "reason": "no_test_command_detected",
            "commands": [],
        }

    shell_result = ShellRunner(project_root).run(selected.command, approved=True)
    return {
        "requested": True,
        "status": "passed" if shell_result.exit_code == 0 else "failed",
        "commands": [
            {
                "command": selected.command,
                "exit_code": shell_result.exit_code,
                "executed": shell_result.executed,
                "tool": selected.tool,
            }
        ],
    }


def _build_agent_run_summary(
    project_root: Path,
    result: AgentRunResult,
    loop: AgentLoop,
    validation: dict[str, Any],
) -> dict[str, Any]:
    """Build the compact human/JSON summary for ``sac agent run``."""
    tools_used: list[str] = []
    files_changed: list[str] = []

    typed = loop.last_typed_result
    if typed is not None:
        tools_used.append(typed.kind)

    pending = result.state.pending_action or {}
    files = pending.get("files")
    if isinstance(files, list):
        files_changed.extend(str(item) for item in files)

    journal = AgentJournalStore(project_root)
    try:
        events = journal.read(result.state.session_id)
    except ValueError:
        events = []
    for event in events:
        if event.type in {"command", "mcp_call", "subagent_dispatch", "patch_proposed"}:
            tools_used.append(event.type)
        if event.type == "patch_proposed":
            proposal = event.payload.get("patch_proposal")
            if isinstance(proposal, dict):
                event_files = proposal.get("files")
                if isinstance(event_files, list):
                    files_changed.extend(str(item) for item in event_files)

    if validation.get("requested"):
        tools_used.append("run_tests")

    return {
        "tools_used": _stable_unique(tools_used),
        "files_changed": _stable_unique(files_changed),
        "validation": validation,
        "rollback_command": f"sac rollback --session {shlex.quote(result.state.session_id)}",
    }


def _stable_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _format_validation_line(validation: dict[str, Any]) -> str:
    status = validation.get("status", "unknown")
    commands = validation.get("commands") or []
    if commands:
        first = commands[0]
        return f"{first.get('command')} {status.upper()}"
    reason = validation.get("reason")
    return f"{status} ({reason})" if reason else str(status)
