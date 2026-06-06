"""Experimental sac memory CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.memory.facade import MemoryFacade

memory_app = typer.Typer(help="[EXPERIMENTAL] Inspect and update unified project memory.")


def _print_json(command: str, status: str, data: Optional[dict] = None, error: Optional[str] = None) -> None:
    print(render_json(CLIJSONResponse(command=command, status=status, data=data or {}, error=error)))


def _selected_scope(
    *,
    project: bool,
    task: bool,
    recent_failures: bool,
    recent_edits: bool,
    pinned: bool,
) -> str:
    selected = [
        ("project", project),
        ("task", task),
        ("recent-failures", recent_failures),
        ("recent-edits", recent_edits),
        ("pinned", pinned),
    ]
    scopes = [name for name, enabled in selected if enabled]
    if len(scopes) > 1:
        raise ValueError("Select exactly one memory scope.")
    return scopes[0] if scopes else "project"


@memory_app.command("show")
def show(
    project: bool = typer.Option(False, "--project", help="Show project notes."),
    task: bool = typer.Option(False, "--task", help="Show task notes."),
    recent_failures: bool = typer.Option(False, "--recent-failures", help="Show recent failing command memory."),
    recent_edits: bool = typer.Option(False, "--recent-edits", help="Show recent edit memory."),
    pinned: bool = typer.Option(False, "--pinned", help="Show pinned files."),
    task_id: Optional[str] = typer.Option(None, "--task-id", help="Task id for --task."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Show redacted unified memory."""
    facade = MemoryFacade(Path.cwd())
    try:
        scope = _selected_scope(project=project, task=task, recent_failures=recent_failures, recent_edits=recent_edits, pinned=pinned)
        if scope == "project":
            data = {"scope": scope, "text": facade.read_project_notes()}
        elif scope == "task":
            if not task_id:
                raise ValueError("--task-id is required with --task.")
            data = {"scope": scope, "task_id": task_id, "text": facade.read_task_notes(task_id)}
        elif scope == "recent-failures":
            data = {"scope": scope, "entries": facade.read_recent_failures()}
        elif scope == "recent-edits":
            data = {"scope": scope, "entries": facade.read_recent_edits()}
        else:
            data = {"scope": scope, "pinned_files": facade.read_pinned_files()}
    except ValueError as exc:
        if json_output:
            _print_json("memory show", "error", error=str(exc))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if json_output:
        _print_json("memory show", "success", data=data)
        return

    if scope in {"project", "task"}:
        console.print(data["text"] or "[yellow]No memory found.[/yellow]")
    elif scope == "pinned":
        pins = data["pinned_files"]
        if not pins:
            console.print("[yellow]No pinned files.[/yellow]")
        else:
            console.print("\n".join(pins))
    else:
        table = Table(title=f"SafeCode Memory: {scope}")
        table.add_column("Timestamp")
        table.add_column("Command")
        table.add_column("Exit")
        table.add_column("Summary")
        for entry in data["entries"]:
            table.add_row(
                str(entry.get("timestamp", "")),
                str(entry.get("command", "")),
                str(entry.get("exit_code", "")),
                str(entry.get("tail_summary", ""))[:120],
            )
        console.print(table if data["entries"] else "[yellow]No entries.[/yellow]")


@memory_app.command("pin")
def pin(path: Path, json_output: bool = typer.Option(False, "--json", help="Output result as JSON.")) -> None:
    """Pin a project file for context selection."""
    try:
        pinned = MemoryFacade(Path.cwd()).pin_file(path)
    except ValueError as exc:
        if json_output:
            _print_json("memory pin", "error", error=str(exc))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        _print_json("memory pin", "success", data={"path": pinned})
    else:
        console.print(f"[green]Pinned:[/green] {pinned}")


@memory_app.command("unpin")
def unpin(path: Path, json_output: bool = typer.Option(False, "--json", help="Output result as JSON.")) -> None:
    """Remove a pinned project file."""
    try:
        unpinned = MemoryFacade(Path.cwd()).unpin_file(path)
    except ValueError as exc:
        if json_output:
            _print_json("memory unpin", "error", error=str(exc))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        _print_json("memory unpin", "success", data={"path": unpinned})
    else:
        console.print(f"[green]Unpinned:[/green] {unpinned}")


@memory_app.command("add-note")
def add_note(
    text: str,
    task_id: Optional[str] = typer.Option(None, "--task-id", help="Attach the note to task memory."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Add a non-secret project or task note."""
    try:
        path = MemoryFacade(Path.cwd()).add_note(text, task_id=task_id)
    except ValueError as exc:
        if json_output:
            _print_json("memory add-note", "error", error=str(exc))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        _print_json("memory add-note", "success", data={"path": path.as_posix(), "task_id": task_id})
    else:
        console.print(f"[green]Memory note added:[/green] {path}")


@memory_app.command("clear")
def clear(
    project: bool = typer.Option(False, "--project", help="Clear project notes."),
    task: bool = typer.Option(False, "--task", help="Clear task notes."),
    recent_failures: bool = typer.Option(False, "--recent-failures", help="Clear recent failures."),
    recent_edits: bool = typer.Option(False, "--recent-edits", help="Clear recent edits."),
    pinned: bool = typer.Option(False, "--pinned", help="Clear pinned files."),
    task_id: Optional[str] = typer.Option(None, "--task-id", help="Task id for --task."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm the destructive clear operation."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Clear one memory scope after confirmation."""
    try:
        scope = _selected_scope(project=project, task=task, recent_failures=recent_failures, recent_edits=recent_edits, pinned=pinned)
        if not any([project, task, recent_failures, recent_edits, pinned]):
            raise ValueError("Select a memory scope to clear.")
        if not yes:
            confirmed = typer.confirm(f"Clear {scope} memory?", default=False)
            if not confirmed:
                if json_output:
                    _print_json("memory clear", "cancelled", data={"scope": scope})
                else:
                    console.print("[yellow]Clear cancelled.[/yellow]")
                raise typer.Exit(code=0)
        MemoryFacade(Path.cwd()).clear(scope, task_id=task_id)
    except ValueError as exc:
        if json_output:
            _print_json("memory clear", "error", error=str(exc))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if json_output:
        _print_json("memory clear", "success", data={"scope": scope, "task_id": task_id})
    else:
        console.print(f"[green]Cleared {scope} memory.[/green]")
