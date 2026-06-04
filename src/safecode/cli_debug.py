"""Experimental debug commands for local failure inspection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import typer
from rich.table import Table

from safecode.audit.logger import AuditLogger
from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.context.redactor import redact_secrets
from safecode.core.failure_category import (
    FailureCategory,
    normalize_failure_category,
    suggested_command_for_category,
)
from safecode.logs.runtime import RuntimeLogger
from safecode.memory.facade import MemoryFacade
from safecode.task.store import TaskStore
from safecode.debug.bundle import create_debug_bundle

debug_app = typer.Typer(help="[EXPERIMENTAL] Inspect local debug artifacts.")


@dataclass(frozen=True)
class LastFailure:
    """Normalized last-failure result for CLI rendering."""

    category: str
    message: str
    command: str | None = None
    file: str | None = None
    task_id: str | None = None
    source: str = "unknown"
    timestamp: str | None = None

    def to_data(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "command": self.command,
            "file": self.file,
            "message": self.message,
            "source": self.source,
            "suggested_next_command": suggested_command_for_category(self.category),
            "task_id": self.task_id,
            "timestamp": self.timestamp,
        }


def find_last_failure(project_root: Path, task_id: str | None = None) -> LastFailure | None:
    """Read SafeCode local artifacts and return the newest known failure."""
    candidates: list[LastFailure] = []
    candidates.extend(_runtime_candidates(project_root, task_id))
    candidates.extend(_task_candidates(project_root, task_id))
    candidates.extend(_memory_candidates(project_root, task_id))
    candidates.extend(_audit_candidates(project_root, task_id))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.timestamp or "", reverse=True)[0]


@debug_app.command("last-failure")
def last_failure(
    task: Optional[str] = typer.Option(None, "--task", help="[EXPERIMENTAL] Filter to a task id."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Show the latest redacted local failure without executing commands."""
    project_root = Path.cwd()
    failure = find_last_failure(project_root, task_id=task)
    if failure is None:
        data = {
            "category": None,
            "command": None,
            "file": None,
            "message": "No failure found.",
            "source": None,
            "suggested_next_command": None,
            "task_id": task,
            "timestamp": None,
        }
        if json_output:
            print(render_json(CLIJSONResponse(command="debug last-failure", status="success", data=data)))
            return
        console.print("[green]No failure found.[/green]")
        return

    data = failure.to_data()
    if json_output:
        print(render_json(CLIJSONResponse(command="debug last-failure", status="success", data=data)))
        return

    table = Table(title="SafeCode Last Failure [EXPERIMENTAL]")
    table.add_column("Field")
    table.add_column("Value")
    for key in (
        "category",
        "message",
        "command",
        "file",
        "task_id",
        "source",
        "suggested_next_command",
    ):
        value = data.get(key)
        if value is not None:
            table.add_row(key, str(value))
    console.print(table)


@debug_app.command("bundle")
def bundle(
    task: Optional[str] = typer.Option(None, "--task", help="[EXPERIMENTAL] Include a selected task sidecar."),
    out: Optional[Path] = typer.Option(None, "--out", help="Output tar.gz path."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing output path."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Create a redacted local debug bundle without project source code."""
    project_root = Path.cwd()
    try:
        result = create_debug_bundle(project_root, task_id=task, out_path=out, force=force)
    except (FileExistsError, ValueError) as exc:
        if json_output:
            print(render_json(CLIJSONResponse(command="debug bundle", status="error", error=str(exc))))
            return
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    data = {
        "path": str(result.path),
        "size_bytes": result.size_bytes,
        "manifest": result.manifest,
    }
    if json_output:
        print(render_json(CLIJSONResponse(command="debug bundle", status="success", data=data)))
        return
    console.print(f"[green]Debug bundle written:[/green] {result.path}")


def _runtime_candidates(project_root: Path, task_id: str | None) -> list[LastFailure]:
    events = RuntimeLogger(project_root).read_recent(limit=200)
    results: list[LastFailure] = []
    for event in events:
        if event.level != "error" and not event.failure_category:
            continue
        details = event.details or {}
        event_task = details.get("task_id")
        if task_id and event_task != task_id:
            continue
        command = details.get("command") or details.get("cmd")
        file_name = details.get("file") or details.get("path")
        results.append(
            LastFailure(
                category=normalize_failure_category(event.failure_category),
                message=redact_secrets(event.message),
                command=redact_secrets(command) if command else None,
                file=redact_secrets(file_name) if file_name else None,
                task_id=event_task,
                source="runtime_log",
                timestamp=event.timestamp,
            )
        )
    return results


def _task_candidates(project_root: Path, task_id: str | None) -> list[LastFailure]:
    store = TaskStore(project_root)
    states = [store.load(task_id)] if task_id else list(store.list())
    results: list[LastFailure] = []
    for state in states:
        if state is None:
            continue
        for iteration in state.iterations:
            category = normalize_failure_category(iteration.failure_category)
            is_failure = bool(iteration.failure_category) or iteration.status == "failed"
            if not is_failure:
                continue
            command = iteration.test_command or (state.last_command.command if state.last_command else None)
            message = iteration.status or iteration.event
            if iteration.test_exit_code is not None:
                message = f"{message}; exit_code={iteration.test_exit_code}"
            results.append(
                LastFailure(
                    category=category,
                    message=redact_secrets(message),
                    command=redact_secrets(command) if command else None,
                    file=redact_secrets(iteration.pending_patch_path) if iteration.pending_patch_path else None,
                    task_id=state.task_id,
                    source="task_sidecar",
                    timestamp=iteration.timestamp or iteration.created_at,
                )
            )
    return results


def _memory_candidates(project_root: Path, task_id: str | None) -> list[LastFailure]:
    try:
        entries = MemoryFacade(project_root).read_recent_failures(limit=200)
    except Exception:
        return []
    results: list[LastFailure] = []
    for entry in entries:
        entry_task = entry.get("task_id")
        if task_id and entry_task != task_id:
            continue
        exit_code = entry.get("exit_code")
        category = FailureCategory.COMMAND_TIMEOUT.value if exit_code == 124 else FailureCategory.UNKNOWN.value
        message = str(entry.get("tail_summary") or f"command failed with exit_code={exit_code}")
        results.append(
            LastFailure(
                category=category,
                message=redact_secrets(message),
                command=redact_secrets(str(entry.get("command") or "")) or None,
                task_id=str(entry_task) if entry_task else None,
                source="recent_failures_memory",
                timestamp=str(entry.get("timestamp") or ""),
            )
        )
    return results


def _audit_candidates(project_root: Path, task_id: str | None) -> list[LastFailure]:
    try:
        events = AuditLogger(project_root).read_recent(limit=200)
    except Exception:
        return []
    results: list[LastFailure] = []
    for event in events:
        event_task = event.metadata.get("task_id")
        if task_id and event_task != task_id:
            continue
        if event.status not in {"failed", "blocked", "error"} and not event.error:
            continue
        category = _category_from_audit(event)
        message = event.error or event.message or event.type
        results.append(
            LastFailure(
                category=category,
                message=redact_secrets(message),
                command=redact_secrets(event.command) if event.command else None,
                file=", ".join(redact_secrets(path) for path in event.files) if event.files else None,
                task_id=event_task,
                source="audit_event",
                timestamp=event.timestamp,
            )
        )
    return results


def _category_from_audit(event) -> str:
    if event.exit_code == 124:
        return FailureCategory.COMMAND_TIMEOUT.value
    if event.status == "blocked" or event.exit_code in {125, 126}:
        text = f"{event.message or ''} {event.error or ''}".lower()
        if "network" in text:
            return FailureCategory.NETWORK_DISABLED.value
        if event.type.startswith("sandbox"):
            return FailureCategory.SANDBOX_PREFLIGHT_FAILED.value
        return FailureCategory.COMMAND_BLOCKED_BY_POLICY.value
    if event.type.startswith("rollback") or event.type.startswith("patch"):
        return FailureCategory.PATCH_APPLY_CONFLICT.value
    return FailureCategory.UNKNOWN.value
