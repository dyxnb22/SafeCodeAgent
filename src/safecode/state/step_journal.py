"""Structured per-step task journal for long-running agent sessions."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from safecode.context.redactor import redact_secrets
from safecode.utils.time import utc_now_iso


@dataclass(frozen=True)
class StepJournalEntry:
    """One compact, resume-friendly agent step record."""

    step_id: str
    session_id: str
    step_index: int
    action_type: str
    tool_name: str = ""
    files_read: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    outcome: str = "success"
    summary: str = ""
    timestamp: str = field(default_factory=utc_now_iso)
    payload_version: int = 1


class StepJournalStore:
    """Append-only JSONL store under ``.sac/tasks/<session_id>/``."""

    def __init__(self, project_root: Path, *, cap: int = 500) -> None:
        self.project_root = project_root
        self.cap = cap

    def append(self, entry: StepJournalEntry) -> None:
        path = self._path(entry.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.read(entry.session_id)
        existing.append(entry)
        if len(existing) > self.cap:
            existing = existing[-self.cap:]
        lines = []
        for item in existing:
            data = asdict(item)
            data["summary"] = redact_secrets(str(data.get("summary", "")))[:1000]
            lines.append(json.dumps(data, ensure_ascii=False, sort_keys=True))
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def read(self, session_id: str) -> list[StepJournalEntry]:
        path = self._path(session_id)
        if not path.is_file():
            return []
        entries: list[StepJournalEntry] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                data = json.loads(line)
                entries.append(StepJournalEntry(**data))
        except Exception:
            return []
        return entries

    def _path(self, session_id: str) -> Path:
        return self.project_root / ".sac" / "tasks" / session_id / "step_journal.jsonl"
