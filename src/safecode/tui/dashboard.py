"""Rich dashboard for daily SafeCode Agent status (v2.3.0)."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.agent.session import AgentSessionStore
from safecode.patch.diff import build_unified_diff
from safecode.patch.models import PatchProposal
from safecode.state.journal import AgentJournalStore


def render_dashboard(project_root: Path, *, history_limit: int = 8) -> str:
    """Render a compact terminal dashboard for the current project."""
    console = Console(record=True, width=120)
    console.print(_build_dashboard(project_root, history_limit=history_limit))
    return console.export_text()


def _build_dashboard(project_root: Path, *, history_limit: int) -> Panel:
    store = AgentSessionStore(project_root)
    state = store.load()

    panels = [
        _session_panel(state),
        _plan_panel(state),
        _pending_action_panel(state),
        _pending_patch_panel(project_root),
        _history_panel(project_root, state.session_id if state else None, history_limit),
    ]
    return Panel(Group(*panels), title="SafeCode TUI", border_style="cyan")


def _session_panel(state: object | None) -> Panel:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    if state is None:
        table.add_row("Session", "No active session")
        table.add_row("Next", "Run sac agent start \"goal\" or sac agent step \"goal\"")
    else:
        table.add_row("Session", state.session_id)
        table.add_row("Goal", state.goal)
        table.add_row("Status", state.status)
        table.add_row("Step", f"{state.current_step}/{len(state.plan)}")
        table.add_row("Last Observation", state.last_observation or "(none)")
        table.add_row("Last Error", state.last_error or "(none)")
    return Panel(table, title="Session", border_style="green")


def _plan_panel(state: object | None) -> Panel:
    table = Table(title=None)
    table.add_column("#", justify="right")
    table.add_column("Plan Item")
    table.add_column("State")
    if state is None or not state.plan:
        table.add_row("-", "No plan recorded", "")
    else:
        for index, item in enumerate(state.plan):
            status = "done" if index < state.current_step else "next" if index == state.current_step else "pending"
            table.add_row(str(index + 1), item, status)
    return Panel(table, title="Plan", border_style="blue")


def _pending_action_panel(state: object | None) -> Panel:
    if state is None or not state.pending_action:
        content = "(none)"
    else:
        content = json.dumps(state.pending_action, indent=2, ensure_ascii=False, sort_keys=True)
    return Panel(Syntax(content, "json" if content != "(none)" else "text", theme="ansi_dark"), title="Approval / Action", border_style="yellow")


def _pending_patch_panel(project_root: Path) -> Panel:
    pending_path = project_root / ".sac" / "pending_patch.json"
    if not pending_path.exists() or pending_path.is_symlink():
        return Panel("(none)", title="Pending Diff", border_style="magenta")
    try:
        proposal = PatchProposal.model_validate_json(pending_path.read_text(encoding="utf-8"))
        diff_text = build_unified_diff(project_root, proposal)
    except Exception as exc:
        diff_text = f"Unable to render pending patch: {exc}"
    return Panel(Syntax(diff_text or "(empty diff)", "diff", theme="ansi_dark"), title="Pending Diff", border_style="magenta")


def _history_panel(project_root: Path, session_id: str | None, history_limit: int) -> Panel:
    journal = AgentJournalStore(project_root)
    selected_session_id = session_id or journal.latest_session_id()
    if not selected_session_id:
        return Panel("No journal events found.", title="History", border_style="white")
    try:
        events = journal.read(selected_session_id)[-history_limit:]
    except Exception as exc:
        return Panel(f"Unable to read journal: {exc}", title="History", border_style="white")
    table = Table(title=None)
    table.add_column("Step")
    table.add_column("Type")
    table.add_column("Message")
    for event in events:
        table.add_row("" if event.step is None else str(event.step), event.type, event.message)
    return Panel(table if events else "No journal events found.", title="History", border_style="white")
