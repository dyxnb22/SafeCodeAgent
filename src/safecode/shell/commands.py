"""Slash-command dispatch for the unified conversational shell."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from safecode.shell.memory import render_context_ledger
from safecode.shell.rendering import history_text


def dispatch_local_command(
    command: str,
    *,
    project_root: Path,
    conversation: Any,
    legacy_dispatch: Callable[[str, Path, str | None], tuple[str, str, bool]],
) -> tuple[str, bool]:
    """Handle commands that need conversation state, then delegate stable commands."""
    name = command.split(None, 1)[0].lower()
    if command.strip().lower() == "/memory why":
        return render_context_ledger(project_root), False
    if name == "/history":
        return history_text(conversation), False
    response, _intent, should_exit = legacy_dispatch(command, project_root, None)
    return response, should_exit
