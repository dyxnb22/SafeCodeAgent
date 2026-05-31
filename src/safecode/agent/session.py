"""File-backed interactive agent session state."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from safecode.state.journal import AgentJournalStore
from safecode.utils.time import utc_now_iso


class AgentSessionState(BaseModel):
    """Persisted state for a bounded interactive agent session."""

    session_id: str
    goal: str
    plan: list[str] = Field(default_factory=list)
    current_step: int = 0
    pending_action: dict[str, object] | None = None
    last_observation: str = ""
    status: str = "active"
    last_error: str | None = None
    created_at: str
    updated_at: str


class AgentSessionStore:
    """Store one current agent session under ``.sac/session.json``."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.path = project_root / ".sac" / "session.json"

    def start(self, goal: str, plan: list[str] | None = None) -> AgentSessionState:
        """Create or replace the current session."""
        planned_steps = list(plan or [])
        now = utc_now_iso()
        state = AgentSessionState(
            session_id=uuid4().hex,
            goal=goal,
            plan=planned_steps,
            current_step=0,
            pending_action=None,
            last_observation="Session created.",
            status="active",
            created_at=now,
            updated_at=now,
        )
        self.save(state)
        AgentJournalStore(self.project_root).record_plan(state.session_id, goal, planned_steps)
        return state

    def load(self) -> AgentSessionState | None:
        """Load the current session, returning None if missing or invalid."""
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return AgentSessionState(**data)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return None

    def save(self, state: AgentSessionState) -> AgentSessionState:
        """Persist session state atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        updated = state.model_copy(update={"updated_at": utc_now_iso()})
        self._atomic_write_text(updated.model_dump_json(indent=2) + "\n")
        return updated

    def clear(self) -> bool:
        """Remove the current session file."""
        if self.path.exists():
            self.path.unlink()
            return True
        return False

    def abort(self, reason: str = "aborted by user") -> AgentSessionState:
        """Mark the current session as aborted."""
        state = self.load()
        if state is None:
            raise FileNotFoundError("No agent session found.")
        updated = state.model_copy(
            update={
                "status": "aborted",
                "last_error": reason,
                "last_observation": f"Session aborted: {reason}",
                "pending_action": None,
            }
        )
        saved = self.save(updated)
        AgentJournalStore(self.project_root).record_failure(
            saved.session_id,
            saved.last_observation,
            {"reason": reason, "status": saved.status},
        )
        return saved

    def resume(self) -> AgentSessionState:
        """Resume an existing non-completed session."""
        state = self.load()
        if state is None:
            raise FileNotFoundError("No agent session found.")
        if state.status == "completed":
            raise ValueError("Completed sessions cannot be resumed.")
        updated = state.model_copy(
            update={
                "status": "active",
                "last_observation": "Session resumed.",
                "last_error": None,
            }
        )
        return self.save(updated)

    def explain_last_failure(self) -> str:
        """Return a short explanation of the latest recoverable failure."""
        state = self.load()
        if state is None:
            raise FileNotFoundError("No agent session found.")
        if state.last_error:
            return state.last_error
        if state.status == "completed":
            return "The current session is completed and has no recorded failure."
        return "No failure has been recorded for the current session."

    def _atomic_write_text(self, text: str) -> None:
        tmp_path = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            tmp_path.write_text(text, encoding="utf-8")
            os.replace(tmp_path, self.path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
