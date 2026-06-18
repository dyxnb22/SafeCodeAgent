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
from safecode.agent.conversation import ConversationBuffer
from safecode.agent.session import AgentSessionState, AgentSessionStore
from safecode.shell.session import ShellSessionManager, ShellSessionManifest
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
    manager = ShellSessionManager(project_root / ".sac")
    rows = []
    for state in manager.list():
        rows.append({
            "kind": "conversation",
            "session_id": state.session_id,
            "task_id": state.task_id,
            "turns": state.turns,
            "title": state.title,
            "status": state.status,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
        })
    known_ids = {row["session_id"] for row in rows}
    legacy_store = ShellSessionStore(project_root)
    for legacy_id in legacy_store.list_sessions():
        if legacy_id in known_ids:
            continue
        migrated = _load_or_migrate_manifest(project_root, legacy_id)
        if migrated is None:
            continue
        rows.append({
            "kind": "conversation",
            "session_id": migrated.session_id,
            "task_id": migrated.task_id,
            "turns": migrated.turns,
            "title": migrated.title,
            "status": migrated.status,
            "created_at": migrated.created_at,
            "updated_at": migrated.updated_at,
        })
        known_ids.add(migrated.session_id)
    journal = AgentJournalStore(project_root)
    for session_id in _agent_journal_ids(journal):
        if session_id in known_ids:
            continue
        summary = journal.summary(session_id)
        rows.append({
            "kind": "agent",
            "session_id": session_id,
            "task_id": "",
            "turns": summary.event_count,
            "title": "Legacy agent session",
            "status": "legacy",
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
    table.add_column("Title")
    table.add_column("Events", justify="right")
    table.add_column("Updated")
    for row in rows:
        table.add_row(row["kind"], row["session_id"], row["task_id"] or "", row["title"], str(row["turns"]), row["updated_at"])
    console.print(table if rows else "[dim]No sessions found.[/dim]")


@session_app.command("show")
def show_session(
    session_id: str = typer.Argument(..., help="Session id to show."),
    timeline: bool = typer.Option(False, "--timeline", help="Show agent journal timeline."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Show a shell or agent session."""
    project_root = Path.cwd()
    manager = ShellSessionManager(project_root / ".sac")
    manifest = _load_or_migrate_manifest(project_root, session_id)
    shell_state = ShellSessionStore(project_root).load(session_id) if manifest is None else None
    rows = build_session_timeline(project_root, session_id) if timeline else []
    if manifest is None and shell_state is None and not rows:
        _emit_error("session show", f"Session not found: {session_id}", json_output)
        raise typer.Exit(code=1)
    data = {
        "session_id": session_id,
        "kind": "conversation" if manifest is not None else ("shell" if shell_state is not None else "agent"),
        "turns": manifest.turns if manifest is not None else (len(shell_state.turns) if shell_state is not None else None),
        "title": manifest.title if manifest is not None else None,
        "status": manifest.status if manifest is not None else None,
        "timeline": [row.__dict__ for row in rows],
    }
    if json_output:
        print(render_json(CLIJSONResponse(command="session show", status="success", data=data)))
        return
    if timeline:
        console.print(render_session_timeline(project_root, session_id))
        return
    if manifest is not None:
        console.print(
            f"Conversation {session_id}: {manifest.title}\n"
            f"Status: {manifest.status}\nTurns: {manifest.turns}\nMode: {manifest.mode}"
        )
    elif shell_state is not None:
        console.print(f"Shell session {session_id}: {len(shell_state.turns)} turn(s).")


@session_app.command("resume")
def resume_session(
    session_id: str = typer.Argument(..., help="Agent session id to resume from journal/current state."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Select a conversation as the latest session without executing it."""
    project_root = Path.cwd()
    manager = ShellSessionManager(project_root / ".sac")
    manifest = manager.load(session_id)
    if manifest is None:
        legacy = AgentSessionStore(project_root).load_by_id(session_id)
        if legacy is not None:
            manifest = manager.save(ShellSessionManifest(
                session_id=legacy.session_id,
                title=legacy.goal[:60] or "Imported agent session",
                status=legacy.status,
                agent_session_id=legacy.session_id,
            ))
        else:
            _emit_error("session resume", f"Cannot resume session {session_id}: not found", json_output)
            raise typer.Exit(code=1)
    manifest = manager.save(manifest.model_copy(update={"status": "active", "interrupted": False}))
    data = {
        "session_id": manifest.session_id,
        "status": manifest.status,
        "turns": manifest.turns,
        "title": manifest.title,
    }
    if json_output:
        print(render_json(CLIJSONResponse(command="session resume", status="success", data=data)))
    else:
        console.print(
            f"Selected conversation {manifest.session_id}: {manifest.title}\n"
            f"Next: sac --resume {manifest.session_id}"
        )


@session_app.command("stats")
def session_stats(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Show aggregate session/task stats."""
    project_root = Path.cwd()
    shell_store = ShellSessionManager(project_root / ".sac")
    task_store = TaskStore(project_root)
    for legacy_id in ShellSessionStore(project_root).list_sessions():
        _load_or_migrate_manifest(project_root, legacy_id)
    sessions = shell_store.list()
    tasks = list(task_store.list())
    data = {
        "sessions": len(sessions),
        "turns": sum(s.turns for s in sessions),
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
    manager = ShellSessionManager(project_root / ".sac")
    state = _load_or_migrate_manifest(project_root, session_id)
    if state is None:
        _emit_error("session export", f"Session not found: {session_id}", json_output)
        raise typer.Exit(code=1)
    bundle = {
        "format": "safecode-session-v2",
        "manifest": state.model_dump(),
        "conversation": ConversationBuffer.load(session_id, project_root / ".sac").to_messages(),
        "agent": (
            agent.model_dump() if (agent := AgentSessionStore(project_root, session_id=session_id).load()) else None
        ),
    }
    raw = json.dumps(bundle, indent=2, ensure_ascii=False)
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
        if data.get("format") == "safecode-session-v2":
            state = ShellSessionManifest.model_validate(data["manifest"])
        else:
            legacy = ShellSessionState.model_validate(data)
            state = ShellSessionManifest(
                session_id=legacy.session_id,
                task_id=legacy.task_id,
                turns=len(legacy.turns),
                created_at=legacy.created_at,
                updated_at=legacy.updated_at,
                title="Imported legacy conversation",
            )
    except Exception as exc:
        _emit_error("session import", f"Invalid session export: {type(exc).__name__}", json_output)
        raise typer.Exit(code=1) from exc
    store = ShellSessionManager(project_root / ".sac")
    store.save(state)
    if data.get("format") == "safecode-session-v2":
        conversation = ConversationBuffer.load(state.session_id, project_root / ".sac")
        for message in data.get("conversation", []):
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = str(message.get("content", ""))
            if role == "user":
                conversation.append_user(content)
            elif role == "assistant":
                conversation.append_assistant(content)
            elif role == "tool":
                conversation.append_tool_result("imported", content)
        if isinstance(data.get("agent"), dict):
            agent = AgentSessionState.model_validate(data["agent"]).model_copy(
                update={"session_id": state.session_id}
            )
            AgentSessionStore(project_root, session_id=state.session_id).save(agent)
    result = {"session_id": state.session_id, "turns": state.turns}
    if json_output:
        print(render_json(CLIJSONResponse(command="session import", status="success", data=result)))
    else:
        console.print(f"Imported session {state.session_id} ({state.turns} turns).")


def _emit_error(command: str, message: str, json_output: bool) -> None:
    if json_output:
        print(render_json(CLIJSONResponse(command=command, status="error", error=message)))
    else:
        console.print(f"[red]{message}[/red]")


def _load_or_migrate_manifest(
    project_root: Path,
    session_id: str,
) -> ShellSessionManifest | None:
    manager = ShellSessionManager(project_root / ".sac")
    current = manager.load(session_id)
    if current is not None:
        return current
    legacy = ShellSessionStore(project_root).load(session_id)
    if legacy is None:
        return None
    manifest = manager.save(ShellSessionManifest(
        session_id=legacy.session_id,
        task_id=legacy.task_id,
        turns=len(legacy.turns),
        created_at=legacy.created_at,
        updated_at=legacy.updated_at,
        title="Imported legacy conversation",
        status="closed",
    ))
    conversation = ConversationBuffer.load(session_id, project_root / ".sac")
    if conversation.is_empty():
        for turn in legacy.turns:
            conversation.append_user(turn.user_input)
            conversation.append_assistant(turn.shell_response)
    return manifest


def _agent_journal_ids(journal: AgentJournalStore) -> list[str]:
    if not journal.root.exists():
        return []
    return [
        path.stem
        for path in sorted(journal.root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if path.is_file() and not path.is_symlink()
    ]
