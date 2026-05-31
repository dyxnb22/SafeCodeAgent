"""Per-session agent journal storage."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from safecode.utils.time import utc_now_iso


JournalEventType = Literal["plan", "action", "diff", "command", "failure", "final_summary"]


class AgentJournalEvent(BaseModel):
    """One structured journal event for an agent session."""

    event_id: str = Field(default_factory=lambda: uuid4().hex)
    session_id: str
    type: JournalEventType
    message: str
    timestamp: str = Field(default_factory=utc_now_iso)
    step: int | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class AgentJournalSummary(BaseModel):
    """A compact view of one session journal."""

    session_id: str
    path: str
    event_count: int
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    final_message: str | None = None


class AgentJournalStore:
    """Persist append-only-looking journal files with atomic rewrites."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.root = project_root / ".sac" / "agent_journals"

    def path_for(self, session_id: str) -> Path:
        """Return the safe journal path for a session id."""
        self._validate_session_id(session_id)
        return self.root / f"{session_id}.jsonl"

    def append(self, event: AgentJournalEvent) -> AgentJournalEvent:
        """Append one event while replacing the journal file atomically."""
        path = self.path_for(event.session_id)
        events = self.read(event.session_id)
        events.append(event)
        self._atomic_write_jsonl(path, events)
        return event

    def record_plan(self, session_id: str, goal: str, plan: list[str]) -> AgentJournalEvent:
        return self.append(
            AgentJournalEvent(
                session_id=session_id,
                type="plan",
                message=f"Planned {len(plan)} step(s) for goal.",
                payload={"goal": goal, "steps": list(plan)},
            )
        )

    def record_action(
        self,
        session_id: str,
        step: int,
        message: str,
        action: dict[str, object] | None = None,
    ) -> AgentJournalEvent:
        return self.append(
            AgentJournalEvent(
                session_id=session_id,
                type="action",
                step=step,
                message=message,
                payload={"action": dict(action or {})},
            )
        )

    def record_diff(self, session_id: str, message: str, diff_summary: dict[str, object]) -> AgentJournalEvent:
        return self.append(
            AgentJournalEvent(
                session_id=session_id,
                type="diff",
                message=message,
                payload={"diff": dict(diff_summary)},
            )
        )

    def record_command(self, session_id: str, message: str, command_summary: dict[str, object]) -> AgentJournalEvent:
        return self.append(
            AgentJournalEvent(
                session_id=session_id,
                type="command",
                message=message,
                payload={"command": dict(command_summary)},
            )
        )

    def record_failure(self, session_id: str, message: str, details: dict[str, object] | None = None) -> AgentJournalEvent:
        return self.append(
            AgentJournalEvent(
                session_id=session_id,
                type="failure",
                message=message,
                payload={"details": dict(details or {})},
            )
        )

    def record_final_summary(
        self, session_id: str, message: str, summary: dict[str, object] | None = None
    ) -> AgentJournalEvent:
        return self.append(
            AgentJournalEvent(
                session_id=session_id,
                type="final_summary",
                message=message,
                payload={"summary": dict(summary or {})},
            )
        )

    def read(self, session_id: str) -> list[AgentJournalEvent]:
        """Read valid journal events for one session."""
        path = self.path_for(session_id)
        if not path.exists() or path.is_symlink():
            return []
        events: list[AgentJournalEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(AgentJournalEvent(**json.loads(line)))
        return events

    def latest_session_id(self) -> str | None:
        """Return the session id for the newest journal file."""
        if not self.root.exists():
            return None
        candidates = [
            path
            for path in self.root.glob("*.jsonl")
            if path.is_file() and not path.is_symlink() and self._is_valid_session_id(path.stem)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return candidates[0].stem

    def summary(self, session_id: str) -> AgentJournalSummary:
        """Return a compact journal summary."""
        events = self.read(session_id)
        final = next((event.message for event in reversed(events) if event.type == "final_summary"), None)
        return AgentJournalSummary(
            session_id=session_id,
            path=str(self.path_for(session_id)),
            event_count=len(events),
            first_timestamp=events[0].timestamp if events else None,
            last_timestamp=events[-1].timestamp if events else None,
            final_message=final,
        )

    def render_markdown(self, session_id: str) -> str:
        """Render a session journal as Markdown."""
        events = self.read(session_id)
        lines = [f"# SafeCode Agent Journal: {session_id}", ""]
        if not events:
            lines.append("No journal events found.")
            return "\n".join(lines)
        lines.extend(["| Time | Type | Step | Message |", "|---|---|---:|---|"])
        for event in events:
            message = event.message.replace("|", "\\|")
            step = "" if event.step is None else str(event.step)
            lines.append(f"| {event.timestamp} | {event.type} | {step} | {message} |")
        return "\n".join(lines)

    def _atomic_write_jsonl(self, path: Path, events: list[AgentJournalEvent]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        text = "".join(event.model_dump_json() + "\n" for event in events)
        tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            tmp_path.write_text(text, encoding="utf-8")
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _validate_session_id(self, session_id: str) -> None:
        if not self._is_valid_session_id(session_id):
            raise ValueError("Invalid agent session id.")

    def _is_valid_session_id(self, session_id: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9_-]{8,128}", session_id))
