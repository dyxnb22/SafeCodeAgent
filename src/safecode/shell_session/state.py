"""EXPERIMENTAL: Shell session state model for sac shell (v4.9+).

Session state is persisted to .sac/shell/<session_id>.json.
All fields are optional or have defaults; corrupt files return None on load (fail-safe).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from safecode.utils.time import utc_now_iso

_MAX_TURNS = 50
_SUPPORTED_PAYLOAD_VERSION = 1


class ShellTurn(BaseModel):
    """One recorded user-shell turn."""

    turn_index: int
    user_input: str
    shell_response: str
    intent: str = "unknown"
    task_id: str | None = None
    audit_trace_id: str | None = None
    timestamp: str = Field(default_factory=utc_now_iso)


class ShellSessionState(BaseModel):
    """Lightweight shell session state (experimental, v4.9+).

    Persisted to .sac/shell/<session_id>.json. payload_version > 1 is refused
    on load (fail-closed). Turns are bounded to _MAX_TURNS to prevent unbounded growth.
    """

    session_id: str
    task_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    turns: list[ShellTurn] = Field(default_factory=list)
    payload_version: int = _SUPPORTED_PAYLOAD_VERSION

    def next_turn_index(self) -> int:
        """Return the next turn index."""
        return len(self.turns)

    def bounded_turns(self) -> list[ShellTurn]:
        """Return turns bounded to the most recent _MAX_TURNS entries."""
        return self.turns[-_MAX_TURNS:]

    @classmethod
    def supported_payload_version(cls) -> int:
        return _SUPPORTED_PAYLOAD_VERSION
