"""sac task subcommands (experimental, v4.1+).

All outputs are redacted and support --json via CLIJSONResponse (stable contract 11).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.context.redactor import redact_secrets
from safecode.task.store import TaskStore

task_app = typer.Typer(
    name="task",
    help="[EXPERIMENTAL] Manage task sidecars. (v4.1+)",
    no_args_is_help=True,
)


def _store() -> TaskStore:
    return TaskStore(Path.cwd())


def _state_to_dict(state: object) -> dict:
    """Serialise a TaskState to a redacted plain dict."""
    from safecode.task.state import TaskState
    assert isinstance(state, TaskState)
    d = state.model_dump()
    d["goal"] = redact_secrets(d.get("goal") or "")
    return d


@task_app.command("new")
def task_new(
    goal: str = typer.Argument(..., help="Goal for the new task."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Create a new task and set it as current."""
    if not goal or not goal.strip():
        msg = "Goal must be non-empty."
        if json_output:
            print(render_json(CLIJSONResponse(command="task new", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)
    try:
        state = _store().create(goal)
    except ValueError as exc:
        if json_output:
            print(render_json(CLIJSONResponse(command="task new", status="error", error=str(exc))))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if json_output:
        print(render_json(CLIJSONResponse(
            command="task new",
            status="success",
            data={"task_id": state.task_id, "goal": redact_secrets(state.goal), "status": state.status},
        )))
    else:
        console.print(f"[green]Task created:[/green] {state.task_id}")
        console.print(f"Goal: {redact_secrets(state.goal)}")
        console.print(f"CURRENT set to: {state.task_id}")


@task_app.command("list")
def task_list(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] List all tasks (newest first)."""
    store = _store()
    tasks = store.list()
    current = store.current_id()

    if json_output:
        items = [
            {
                "task_id": s.task_id,
                "goal": redact_secrets(s.goal),
                "status": s.status,
                "created_at": s.created_at,
                "current": s.task_id == current,
            }
            for s in tasks
        ]
        print(render_json(CLIJSONResponse(
            command="task list",
            status="success",
            data={"tasks": items, "count": len(items)},
        )))
        return

    if not tasks:
        console.print("[yellow]No tasks found.[/yellow]")
        return

    from rich.table import Table
    table = Table(title="[EXPERIMENTAL] Tasks")
    table.add_column("ID")
    table.add_column("Status")
    table.add_column("Created")
    table.add_column("Goal")
    table.add_column("Current")
    for s in tasks:
        marker = "*" if s.task_id == current else ""
        table.add_row(
            s.task_id,
            s.status,
            s.created_at,
            redact_secrets(s.goal),
            marker,
        )
    console.print(table)


@task_app.command("show")
def task_show(
    task_id: Optional[str] = typer.Argument(None, help="Task id (default: CURRENT)."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Show details of a task."""
    store = _store()
    tid = task_id or store.current_id()
    if not tid:
        msg = "No task specified and no CURRENT task."
        if json_output:
            print(render_json(CLIJSONResponse(command="task show", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    state = store.load(tid)
    if state is None:
        msg = f"Task not found: {tid}"
        if json_output:
            print(render_json(CLIJSONResponse(command="task show", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    d = _state_to_dict(state)
    if json_output:
        print(render_json(CLIJSONResponse(command="task show", status="success", data=d)))
    else:
        import json as _json
        console.print(f"[bold]Task:[/bold] {state.task_id}")
        console.print(f"Goal: {redact_secrets(state.goal)}")
        console.print(f"Status: {state.status}")
        console.print(f"Created: {state.created_at}")
        console.print(f"Updated: {state.updated_at}")
        if state.pending_patch_id:
            console.print(f"Pending patch: {state.pending_patch_id}")
        if state.audit_trace_ids:
            console.print(f"Audit traces: {', '.join(state.audit_trace_ids)}")
        if state.iterations:
            console.print(f"Iterations: {len(state.iterations)}")
        if state.last_command:
            console.print(f"Last command: {redact_secrets(state.last_command.command)}")


@task_app.command("switch")
def task_switch(
    task_id: str = typer.Argument(..., help="Task id to switch to."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Switch CURRENT to the specified task."""
    store = _store()
    state = store.load(task_id)
    if state is None:
        msg = f"Task not found: {task_id}"
        if json_output:
            print(render_json(CLIJSONResponse(command="task switch", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    store.set_current(task_id)
    if json_output:
        print(render_json(CLIJSONResponse(
            command="task switch",
            status="success",
            data={"task_id": task_id, "status": state.status},
        )))
    else:
        console.print(f"[green]Switched CURRENT to:[/green] {task_id}")


@task_app.command("close")
def task_close(
    task_id: Optional[str] = typer.Argument(None, help="Task id (default: CURRENT)."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Close a task (set status to closed)."""
    store = _store()
    tid = task_id or store.current_id()
    if not tid:
        msg = "No task specified and no CURRENT task."
        if json_output:
            print(render_json(CLIJSONResponse(command="task close", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    state = store.load(tid)
    if state is None:
        msg = f"Task not found: {tid}"
        if json_output:
            print(render_json(CLIJSONResponse(command="task close", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    updated = state.model_copy(update={"status": "closed"})
    store.save(updated)
    if json_output:
        print(render_json(CLIJSONResponse(
            command="task close",
            status="success",
            data={"task_id": tid, "status": "closed"},
        )))
    else:
        console.print(f"[green]Task closed:[/green] {tid}")


@task_app.command("delete")
def task_delete(
    task_id: str = typer.Argument(..., help="Task id to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm deletion without prompting."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Delete a task sidecar. Requires --yes."""
    if not yes:
        msg = "Deletion requires --yes to confirm."
        if json_output:
            print(render_json(CLIJSONResponse(command="task delete", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    store = _store()
    deleted = store.delete(task_id)
    if not deleted:
        msg = f"Task not found: {task_id}"
        if json_output:
            print(render_json(CLIJSONResponse(command="task delete", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    if json_output:
        print(render_json(CLIJSONResponse(
            command="task delete",
            status="success",
            data={"task_id": task_id, "deleted": True},
        )))
    else:
        console.print(f"[green]Task deleted:[/green] {task_id}")
