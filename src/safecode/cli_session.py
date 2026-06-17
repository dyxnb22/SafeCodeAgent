"""Session management commands for terminal workflows."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import typer
from rich.table import Table

from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.context.redactor import redact_secrets
from safecode.report.session_timeline import build_session_timeline, render_session_timeline
from safecode.state.journal import AgentJournalStore
from safecode.shell_session.state import ShellSessionState
from safecode.shell_session.store import ShellSessionStore
from safecode.task.store import TaskStore


session_app = typer.Typer(help="[EXPERIMENTAL] Manage shell and agent sessions.")


@session_app.command("list")
def list_sessions(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """List persisted shell sessions."""
    project_root = Path.cwd()
    store = ShellSessionStore(project_root)
    rows = []
    for session_id in store.list_sessions():
        state = store.load(session_id)
        if state is None:
            continue
        rows.append({
            "kind": "shell",
            "session_id": state.session_id,
            "task_id": state.task_id,
            "turns": len(state.turns),
            "created_at": state.created_at,
            "updated_at": state.updated_at,
        })
    journal = AgentJournalStore(project_root)
    for session_id in _agent_journal_ids(journal):
        summary = journal.summary(session_id)
        rows.append({
            "kind": "agent",
            "session_id": session_id,
            "task_id": "",
            "turns": summary.event_count,
            "created_at": summary.first_timestamp or "",
            "updated_at": summary.last_timestamp or "",
        })
    if json_output:
        print(render_json(CLIJSONResponse(command="session list", status="success", data={"sessions": rows})))
        return
    table = Table(title="SafeCode Sessions")
    table.add_column("Kind")
    table.add_column("Session")
    table.add_column("Task")
    table.add_column("Events", justify="right")
    table.add_column("Updated")
    for row in rows:
        table.add_row(row["kind"], row["session_id"], row["task_id"] or "", str(row["turns"]), row["updated_at"])
    console.print(table if rows else "[dim]No sessions found.[/dim]")


@session_app.command("show")
def show_session(
    session_id: str = typer.Argument(..., help="Session id to show."),
    timeline: bool = typer.Option(False, "--timeline", help="Show agent journal timeline."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Show a shell or agent session."""
    project_root = Path.cwd()
    shell_state = ShellSessionStore(project_root).load(session_id)
    rows = build_session_timeline(project_root, session_id) if timeline else []
    if shell_state is None and not rows:
        _emit_error("session show", f"Session not found: {session_id}", json_output)
        raise typer.Exit(code=1)
    data = {
        "session_id": session_id,
        "kind": "shell" if shell_state is not None else "agent",
        "turns": len(shell_state.turns) if shell_state is not None else None,
        "timeline": [row.__dict__ for row in rows],
    }
    if json_output:
        print(render_json(CLIJSONResponse(command="session show", status="success", data=data)))
        return
    if timeline:
        console.print(render_session_timeline(project_root, session_id))
        return
    if shell_state is not None:
        console.print(f"Shell session {session_id}: {len(shell_state.turns)} turn(s).")


@session_app.command("resume")
def resume_session(
    session_id: str = typer.Argument(..., help="Agent session id to resume from journal/current state."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Passively resume an agent session by id."""
    project_root = Path.cwd()
    try:
        from safecode.agent.loop import AgentLoop

        state = AgentLoop(project_root).resume_from(session_id)
    except Exception as exc:
        _emit_error("session resume", f"Cannot resume session {session_id}: {exc}", json_output)
        raise typer.Exit(code=1) from exc
    data = {
        "session_id": state.session_id,
        "status": state.status,
        "current_step": state.current_step,
        "goal": state.goal,
    }
    if json_output:
        print(render_json(CLIJSONResponse(command="session resume", status="success", data=data)))
    else:
        console.print(
            f"Resumed agent session {state.session_id}\n"
            f"Status: {state.status}\n"
            f"Current step: {state.current_step}/{len(state.plan)}\n"
            f"Next: sac agent run --max-steps 1"
        )


@session_app.command("stats")
def session_stats(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Show aggregate session/task stats."""
    project_root = Path.cwd()
    shell_store = ShellSessionStore(project_root)
    task_store = TaskStore(project_root)
    sessions = [s for sid in shell_store.list_sessions() if (s := shell_store.load(sid)) is not None]
    tasks = list(task_store.list())
    data = {
        "sessions": len(sessions),
        "turns": sum(len(s.turns) for s in sessions),
        "tasks": len(tasks),
        "open_tasks": sum(1 for t in tasks if t.status == "open"),
        "applied_tasks": sum(1 for t in tasks if t.status == "applied"),
    }
    if json_output:
        print(render_json(CLIJSONResponse(command="session stats", status="success", data=data)))
        return
    console.print("Session stats")
    for key, value in data.items():
        console.print(f"  {key}: {value}")


@session_app.command("export")
def export_session(
    session_id: str = typer.Argument(..., help="Shell session id to export."),
    output: str = typer.Option("", "--output", "-o", help="Output file. Defaults to .sac/exports/<id>.json."),
    sanitize: bool = typer.Option(True, "--sanitize/--no-sanitize", help="Redact secrets before writing."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Export one shell session as a portable JSON file."""
    project_root = Path.cwd()
    store = ShellSessionStore(project_root)
    state = store.load(session_id)
    if state is None:
        _emit_error("session export", f"Session not found: {session_id}", json_output)
        raise typer.Exit(code=1)
    raw = state.model_dump_json(indent=2)
    if sanitize:
        raw = redact_secrets(raw)
    out_path = Path(output) if output else project_root / ".sac" / "exports" / f"{session_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(f".{out_path.name}.{uuid4().hex}.tmp")
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, out_path)
    data = {"session_id": session_id, "path": str(out_path), "sanitize": sanitize}
    if json_output:
        print(render_json(CLIJSONResponse(command="session export", status="success", data=data)))
    else:
        console.print(f"Exported session {session_id}: {out_path}")


@session_app.command("import")
def import_session(
    path: str = typer.Argument(..., help="Exported session JSON file."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Import an exported shell session."""
    project_root = Path.cwd()
    src = Path(path)
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
        state = ShellSessionState.model_validate(data)
    except Exception as exc:
        _emit_error("session import", f"Invalid session export: {type(exc).__name__}", json_output)
        raise typer.Exit(code=1) from exc
    store = ShellSessionStore(project_root)
    store.save(state)
    result = {"session_id": state.session_id, "turns": len(state.turns)}
    if json_output:
        print(render_json(CLIJSONResponse(command="session import", status="success", data=result)))
    else:
        console.print(f"Imported session {state.session_id} ({len(state.turns)} turns).")


def _emit_error(command: str, message: str, json_output: bool) -> None:
    if json_output:
        print(render_json(CLIJSONResponse(command=command, status="error", error=message)))
    else:
        console.print(f"[red]{message}[/red]")


def _agent_journal_ids(journal: AgentJournalStore) -> list[str]:
    if not journal.root.exists():
        return []
    return [
        path.stem
        for path in sorted(journal.root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if path.is_file() and not path.is_symlink()
    ]
