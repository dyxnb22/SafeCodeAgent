"""EXPERIMENTAL: Shell session store for sac shell (v4.9+).

Sessions are persisted under .sac/shell/<session_id>.json.
Corrupt or future-versioned files are read fail-safe (return None).
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from pydantic import ValidationError

from safecode.shell_session.state import ShellSessionState, _SUPPORTED_PAYLOAD_VERSION


class ShellSessionStore:
    """Read/write shell sessions under .sac/shell/."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.shell_dir = self.project_root / ".sac" / "shell"

    def create(self, *, task_id: str | None = None) -> ShellSessionState:
        """Create and persist a new shell session."""
        session_id = uuid.uuid4().hex[:16]
        state = ShellSessionState(session_id=session_id, task_id=task_id)
        self.save(state)
        return state

    def load(self, session_id: str) -> ShellSessionState | None:
        """Load a session. Return None on missing file, corrupt JSON, or future payload version."""
        path = self.shell_dir / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if data.get("payload_version", 1) > _SUPPORTED_PAYLOAD_VERSION:
                return None
            return ShellSessionState.model_validate(data)
        except (json.JSONDecodeError, ValidationError, OSError, KeyError):
            return None

    def save(self, state: ShellSessionState) -> None:
        """Atomically persist a session (write to tmp, then os.replace)."""
        self.shell_dir.mkdir(parents=True, exist_ok=True)
        path = self.shell_dir / f"{state.session_id}.json"
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(state.model_dump_json(), encoding="utf-8")
        os.replace(tmp_path, path)

    def list_sessions(self) -> list[str]:
        """Return session IDs found in the shell directory."""
        if not self.shell_dir.exists():
            return []
        return sorted(
            p.stem for p in self.shell_dir.glob("*.json") if not p.name.endswith(".tmp")
        )
