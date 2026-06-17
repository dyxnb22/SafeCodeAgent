"""Human-oriented session timeline projection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from safecode.state.journal import AgentJournalEvent, AgentJournalStore


@dataclass(frozen=True)
class SessionTimelineEvent:
    """Compact row derived from an agent journal event."""

    timestamp: str
    kind: str
    step: int | None
    message: str
    detail: str = ""


def build_session_timeline(project_root: Path, session_id: str, *, limit: int = 50) -> list[SessionTimelineEvent]:
    """Return compact timeline rows for one agent session."""
    events = AgentJournalStore(project_root).read(session_id)
    rows = [_event_to_row(event) for event in events]
    rows = [row for row in rows if row is not None]
    return rows[-limit:]


def render_session_timeline(project_root: Path, session_id: str, *, limit: int = 50) -> str:
    """Render one session timeline as plain text."""
    rows = build_session_timeline(project_root, session_id, limit=limit)
    lines = [f"Session timeline: {session_id}"]
    if not rows:
        lines.append("No timeline events found.")
        return "\n".join(lines)
    for row in rows:
        step = "" if row.step is None else f" step={row.step}"
        detail = f" — {row.detail}" if row.detail else ""
        lines.append(f"{row.timestamp} [{row.kind}{step}] {row.message}{detail}")
    return "\n".join(lines)


def _event_to_row(event: AgentJournalEvent) -> SessionTimelineEvent | None:
    detail = ""
    if event.type == "plan":
        steps = event.payload.get("steps")
        if isinstance(steps, list):
            detail = f"{len(steps)} planned step(s)"
    elif event.type == "command":
        command = event.payload.get("command")
        if isinstance(command, dict):
            raw = command.get("command")
            if isinstance(raw, list):
                detail = " ".join(str(part) for part in raw)
            elif raw is not None:
                detail = str(raw)
            if command.get("exit_code") is not None:
                detail = f"{detail} exit={command.get('exit_code')}".strip()
    elif event.type == "patch_proposed":
        proposal = event.payload.get("patch_proposal")
        if isinstance(proposal, dict):
            files = proposal.get("files")
            if isinstance(files, list) and files:
                detail = ", ".join(str(item) for item in files[:5])
            patch_id = proposal.get("patch_id") or proposal.get("id")
            if patch_id:
                detail = f"{detail} patch={patch_id}".strip()
    elif event.type == "typed_result":
        result = event.payload.get("typed_result")
        if isinstance(result, dict):
            kind = result.get("kind")
            status = result.get("status")
            parts = [str(part) for part in (kind, status) if part]
            detail = " ".join(parts)
    elif event.type == "subagent_dispatch":
        dispatch = event.payload.get("subagent_dispatch")
        if isinstance(dispatch, dict):
            role = dispatch.get("role")
            task_id = dispatch.get("task_id")
            detail = " ".join(str(part) for part in (role, task_id) if part)

    return SessionTimelineEvent(
        timestamp=event.timestamp,
        kind=event.type,
        step=event.step,
        message=event.message,
        detail=detail,
    )
