"""sac status command: show current task, pending patch, and next safe step (experimental, v4.1+)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer

from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.task.state import TaskState
from safecode.task.store import TaskStore


def next_step(state: Optional[TaskState], pending_patch_exists: bool) -> str:
    """Pure function: derive the one-line next safe step from task state.

    Truth table:
    - state is None                          -> "Run: sac task new \"<goal>\" to start a task."
    - state.status == "closed"               -> "Task is closed. Run: sac task new \"<goal>\" to start a new task."
    - state.status == "applied"              -> "Patch applied. Run: sac fix or sac task close to finish."
    - state.status == "interrupted"          -> "Task interrupted. Run: sac resume or sac fix to continue."
    - state.status == "open" + patch exists  -> "Pending patch ready. Run: sac apply to apply it."
    - state.status == "open" + test failed   -> "Tests failing. Run: sac fix to propose a repair patch."
    - state.status == "open" + no patch      -> "Task open. Run: sac edit \"<change>\" to propose a patch."
    """
    if state is None:
        return 'Run: sac task new "<goal>" to start a task.'
    if state.status == "closed":
        return 'Task is closed. Run: sac task new "<goal>" to start a new task.'
    if state.status == "applied":
        return "Patch applied. Run: sac fix or sac task close to finish."
    if state.status == "interrupted":
        return "Task interrupted. Run: sac resume or sac fix to continue."
    # status == "open"
    if pending_patch_exists:
        return "Pending patch ready. Run: sac apply to apply it."
    # Check if last test failed
    if state.iterations:
        last = state.iterations[-1]
        if last.test_exit_code is not None and last.test_exit_code != 0:
            return "Tests failing. Run: sac fix to propose a repair patch."
    return 'Task open. Run: sac edit "<change>" to propose a patch.'


def _pending_patch_exists(project_root: Path) -> bool:
    return (project_root / ".sac" / "pending_patch.json").exists()


def _build_status_data(
    project_root: Path,
    store: TaskStore,
) -> dict:
    """Build the status payload dict without writing any audit events."""
    current_id = store.current_id()
    state: Optional[TaskState] = None
    if current_id:
        state = store.load(current_id)

    patch_exists = _pending_patch_exists(project_root)
    step = next_step(state, patch_exists)

    data: dict = {
        "task_id": state.task_id if state else None,
        "goal": state.goal if state else None,
        "status": state.status if state else None,
        "pending_patch": patch_exists,
        "last_test_command": None,
        "last_test_exit_code": None,
        "last_command": None,
        "next_step": step,
    }

    if state:
        if state.iterations:
            last_iter = state.iterations[-1]
            if last_iter.test_command is not None:
                data["last_test_command"] = last_iter.test_command
            if last_iter.test_exit_code is not None:
                data["last_test_exit_code"] = last_iter.test_exit_code
        if state.last_command:
            data["last_command"] = state.last_command.command

    return data


def register(app: typer.Typer) -> None:
    """Register the status command on the given Typer app."""

    @app.command("status")
    def status_command(
        json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    ) -> None:
        """[EXPERIMENTAL] Show current task, pending patch state, and next safe step."""
        project_root = Path.cwd()
        store = TaskStore(project_root)
        data = _build_status_data(project_root, store)

        if json_output:
            print(render_json(CLIJSONResponse(command="status", status="success", data=data)))
            return

        is_tty = sys.stdout.isatty() if hasattr(sys, "stdout") else False
        _render_status_text(data, use_rich=is_tty)

    import sys

    return status_command


def _render_status_text(data: dict, *, use_rich: bool = True) -> None:
    """Render status to stdout. TTY uses Rich; non-TTY is deterministic plain text."""
    if use_rich:
        from rich.table import Table
        table = Table(title="[EXPERIMENTAL] SafeCode Status", show_header=False)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        _add_status_rows(table, data)
        console.print(table)
        console.print(f"\n[bold]Next:[/bold] {data['next_step']}")
    else:
        _render_status_plain(data)


def _add_status_rows(table: object, data: dict) -> None:
    """Add status rows to a Rich table."""
    table.add_row("Task ID", data.get("task_id") or "(none)")  # type: ignore[attr-defined]
    table.add_row("Goal", data.get("goal") or "(none)")  # type: ignore[attr-defined]
    table.add_row("Status", data.get("status") or "(none)")  # type: ignore[attr-defined]
    table.add_row("Pending Patch", "yes" if data.get("pending_patch") else "no")  # type: ignore[attr-defined]
    if data.get("last_test_command"):
        table.add_row("Last Test", f"{data['last_test_command']} (exit {data.get('last_test_exit_code')})")  # type: ignore[attr-defined]
    if data.get("last_command"):
        table.add_row("Last Command", data["last_command"])  # type: ignore[attr-defined]


def _render_status_plain(data: dict) -> None:
    """Deterministic plain-text status output for non-TTY."""
    lines = [
        f"task_id: {data.get('task_id') or '(none)'}",
        f"goal: {data.get('goal') or '(none)'}",
        f"status: {data.get('status') or '(none)'}",
        f"pending_patch: {'yes' if data.get('pending_patch') else 'no'}",
    ]
    if data.get("last_test_command"):
        lines.append(f"last_test_command: {data['last_test_command']}")
        lines.append(f"last_test_exit_code: {data.get('last_test_exit_code')}")
    if data.get("last_command"):
        lines.append(f"last_command: {data['last_command']}")
    lines.append(f"next_step: {data['next_step']}")
    print("\n".join(lines))
