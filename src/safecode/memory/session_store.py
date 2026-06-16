"""Session summary store for cross-session project memory (v6.2.0)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_MAX_SESSIONS = 50
_MAX_FILES = 20
_MAX_COMMANDS = 10


@dataclass
class SessionSummary:
    """Bounded, redacted summary of one agent session."""

    session_id: str
    goal: str
    started_at: str
    ended_at: str
    stopped_reason: str
    steps: int
    touched_files: list[str]
    commands_run: list[str]
    tests_passed: bool | None
    approved_patches: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionSummary":
        return cls(
            session_id=str(data.get("session_id", "")),
            goal=str(data.get("goal", "")),
            started_at=str(data.get("started_at", "")),
            ended_at=str(data.get("ended_at", "")),
            stopped_reason=str(data.get("stopped_reason", "")),
            steps=int(data.get("steps", 0)),
            touched_files=[str(f) for f in data.get("touched_files", [])],
            commands_run=[str(c) for c in data.get("commands_run", [])],
            tests_passed=data.get("tests_passed"),
            approved_patches=int(data.get("approved_patches", 0)),
        )

    def to_context_block(self) -> str:
        """Format as a compact context block for injection into agent context."""
        lines = [f"- Goal: {self.goal[:120]}"]
        if self.touched_files:
            lines.append(f"  Files: {', '.join(self.touched_files[:5])}")
        if self.commands_run:
            lines.append(f"  Commands: {', '.join(self.commands_run[:3])}")
        if self.tests_passed is not None:
            lines.append(f"  Tests: {'passed' if self.tests_passed else 'failed'}")
        lines.append(f"  Outcome: {self.stopped_reason} ({self.steps} steps)")
        return "\n".join(lines)


class SessionSummaryStore:
    """Append-only JSONL store for session summaries."""

    def __init__(self, sac_dir: Path) -> None:
        self.path = sac_dir / "memory" / "sessions.jsonl"

    def append(self, summary: SessionSummary) -> None:
        entries = self._read_all()
        entries.append(summary.to_dict())
        entries = entries[-_MAX_SESSIONS:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            "".join(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n" for e in entries),
            encoding="utf-8",
        )

    def load_recent(self, limit: int = 5) -> list[SessionSummary]:
        """Return up to *limit* most recent summaries, newest first."""
        entries = self._read_all()
        return [SessionSummary.from_dict(e) for e in reversed(entries)][:limit]

    def clear(self, before_iso: str | None = None) -> int:
        """Remove sessions. If *before_iso* given, remove only those older than it."""
        entries = self._read_all()
        if before_iso is None:
            count = len(entries)
            self.path.unlink(missing_ok=True)
            return count
        kept = [e for e in entries if str(e.get("ended_at", "")) >= before_iso]
        removed = len(entries) - len(kept)
        if removed:
            self.path.write_text(
                "".join(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n" for e in kept),
                encoding="utf-8",
            )
        return removed

    def export_all(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in reversed(self.load_recent(limit=_MAX_SESSIONS))]

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    entries.append(value)
            except json.JSONDecodeError:
                continue
        return entries[-_MAX_SESSIONS:]
