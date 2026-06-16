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


@memory_app.command("list-facts")
def list_facts(
    pending: bool = typer.Option(False, "--pending", help="Show only pending facts."),
    approved: bool = typer.Option(False, "--approved", help="Show only approved facts."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] List project convention facts (pending or approved)."""
    from safecode.memory.facts import ProjectFactStore
    sac_dir = Path.cwd() / ".sac"
    store = ProjectFactStore(sac_dir)

    if pending and approved:
        console.print("[red]Use --pending or --approved, not both.[/red]")
        raise typer.Exit(code=1)

    status_filter = "pending" if pending else ("approved" if approved else None)
    facts = store.list_facts(status=status_filter)

    if json_output:
        _print_json("memory list-facts", "success", data={"facts": [f.to_dict() for f in facts]})
        return

    if not facts:
        label = f" ({status_filter})" if status_filter else ""
        console.print(f"[yellow]No facts found{label}.[/yellow]")
        return

    table = Table(title="[EXPERIMENTAL] Project Convention Facts")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Status")
    table.add_column("Key")
    table.add_column("Value")
    table.add_column("Source")
    for f in facts:
        status_style = "green" if f.status == "approved" else ("yellow" if f.status == "pending" else "red")
        table.add_row(
            f.fact_id[:8],
            f"[{status_style}]{f.status}[/{status_style}]",
            f.key,
            f.value[:60],
            f.source,
        )
    console.print(table)


@memory_app.command("approve-fact")
def approve_fact(
    fact_id: str = typer.Argument(..., help="Fact ID (or prefix) to approve."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Approve a pending project convention fact."""
    from safecode.memory.facts import ProjectFactStore
    from safecode.audit.logger import AuditLogger
    from safecode.audit.models import AuditEvent
    from safecode.utils.time import utc_now_iso

    sac_dir = Path.cwd() / ".sac"
    store = ProjectFactStore(sac_dir)
    try:
        fact = store.approve(fact_id)
    except ValueError as exc:
        if json_output:
            _print_json("memory approve-fact", "error", error=str(exc))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    # Audit-log the approval (fact approval is a write-side event)
    try:
        AuditLogger(Path.cwd()).write(
            AuditEvent(
                type="memory_fact_approved",
                timestamp=utc_now_iso(),
                status="success",
                message=f"{fact.key}: {fact.value[:80]}",
                metadata={"fact_id": fact.fact_id, "key": fact.key, "source": fact.source},
            )
        )
    except Exception:
        pass

    if json_output:
        _print_json("memory approve-fact", "success", data={"fact": fact.to_dict()})
    else:
        console.print(f"[green]Approved:[/green] [{fact.fact_id[:8]}] {fact.key}: {fact.value}")


@memory_app.command("reject-fact")
def reject_fact(
    fact_id: str = typer.Argument(..., help="Fact ID (or prefix) to reject."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Reject a pending project convention fact."""
    from safecode.memory.facts import ProjectFactStore
    sac_dir = Path.cwd() / ".sac"
    store = ProjectFactStore(sac_dir)
    try:
        fact = store.reject(fact_id)
    except ValueError as exc:
        if json_output:
            _print_json("memory reject-fact", "error", error=str(exc))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if json_output:
        _print_json("memory reject-fact", "success", data={"fact": fact.to_dict()})
    else:
        console.print(f"[dim]Rejected: [{fact.fact_id[:8]}] {fact.key}: {fact.value}[/dim]")


@memory_app.command("inspect")
def inspect(
    limit: int = typer.Option(5, "--limit", "-n", help="Number of recent sessions to show."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Show recent session summaries written by the agent loop."""
    from safecode.memory.session_store import SessionSummaryStore
    sac_dir = Path.cwd() / ".sac"
    store = SessionSummaryStore(sac_dir)
    summaries = store.load_recent(limit=limit)

    if json_output:
        _print_json("memory inspect", "success", data={"summaries": [s.to_dict() for s in summaries]})
        return

    if not summaries:
        console.print("[yellow]No session summaries found. Run the agent first.[/yellow]")
        return

    for s in summaries:
        console.print(f"[bold cyan]{s.session_id[:12]}[/bold cyan]  {s.ended_at[:19]}")
        console.print(f"  Goal:    {s.goal[:100]}")
        if s.touched_files:
            console.print(f"  Files:   {', '.join(s.touched_files[:5])}")
        if s.commands_run:
            console.print(f"  Cmds:    {', '.join(s.commands_run[:3])}")
        if s.tests_passed is not None:
            status = "[green]passed[/green]" if s.tests_passed else "[red]failed[/red]"
            console.print(f"  Tests:   {status}")
        console.print(f"  Outcome: {s.stopped_reason}  ({s.steps} steps)")
        console.print()


@memory_app.command("export")
def export(
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output file path (default: stdout)."),
    limit: int = typer.Option(50, "--limit", "-n", help="Max sessions to export."),
) -> None:
    """[EXPERIMENTAL] Export session summaries to JSON."""
    import json as _json
    from safecode.memory.session_store import SessionSummaryStore
    sac_dir = Path.cwd() / ".sac"
    store = SessionSummaryStore(sac_dir)
    data = store.export_all()[:limit]
    text = _json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    if out is not None:
        out.write_text(text, encoding="utf-8")
        console.print(f"[green]Exported {len(data)} session(s) to {out}[/green]")
    else:
        print(text)


@memory_app.command("size")
def size(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Show a read-only byte/file breakdown of .sac/ storage by scope."""
    from safecode.memory.sizing import compute_sac_size
    report = compute_sac_size(Path.cwd())

    data = report.model_dump()

    if json_output:
        _print_json("memory size", "success", data=data)
        return

    if not report.exists:
        console.print("[yellow]No .sac/ directory found.[/yellow]")
        return

    table = Table(title="[EXPERIMENTAL] .sac/ Size Breakdown")
    table.add_column("Scope")
    table.add_column("Bytes", justify="right")
    table.add_column("Files", justify="right")
    for entry in report.scopes:
        table.add_row(entry.name, str(entry.bytes), str(entry.files))
    table.add_row("[bold]Total[/bold]", str(report.total_bytes), str(report.total_files))
    console.print(table)
