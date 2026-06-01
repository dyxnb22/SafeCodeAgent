import json
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from safecode.agent.loop import AgentLoop
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
def agent_resume() -> None:
    """Resume an existing non-completed interactive agent session."""
    try:
        state = AgentSessionStore(Path.cwd()).resume()
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
    max_steps: int = typer.Option(5, "--max-steps", min=1, help="Maximum steps to advance."),
) -> None:
    """Advance a bounded interactive agent loop."""
    try:
        result = AgentLoop(Path.cwd()).run(goal or None, max_steps=max_steps)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

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
            f"Stopped Reason: {result.stopped_reason}",
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


