"""Unified experimental project memory facade."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safecode.context.redactor import redact_secrets

_MAX_RECENT_ENTRIES = 200
_MAX_TAIL_CHARS = 4000
_SENSITIVE_WORDS = frozenset({"token", "secret", "password", "api_key", "apikey", "private_key", "client_secret"})


@dataclass(frozen=True)
class RecentFailureEntry:
    """Bounded recent failure memory entry."""

    task_id: str | None
    command: str
    suite: str | None
    exit_code: int
    tail_hash: str
    tail_summary: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "command": self.command,
            "suite": self.suite,
            "exit_code": self.exit_code,
            "tail_hash": self.tail_hash,
            "tail_summary": self.tail_summary,
            "timestamp": self.timestamp,
        }


class MemoryFacade:
    """Read legacy memory and write only to the v4.6 experimental layout."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.sac_dir = self.project_root / ".sac"
        self.memory_dir = self.sac_dir / "memory"
        self.project_path = self.memory_dir / "project.md"
        self.recent_failures_path = self.memory_dir / "recent-failures.jsonl"
        self.recent_edits_path = self.memory_dir / "recent-edits.jsonl"
        self.pinned_path = self.memory_dir / "pinned-files.txt"

    def read_project_notes(self) -> str:
        """Return redacted new project notes plus legacy read-only memory."""
        sections: list[str] = []
        if self.project_path.exists():
            sections.append(self.project_path.read_text(encoding="utf-8"))

        legacy_memory = self._read_legacy_memory_json()
        if legacy_memory:
            lines = ["## Legacy Memory", ""]
            for key in sorted(legacy_memory):
                lines.append(f"- {key}: {legacy_memory[key]}")
            sections.append("\n".join(lines))

        progress = self._read_if_exists(self.sac_dir / "progress.md")
        if progress:
            sections.append("## Legacy Progress\n\n" + progress)

        rules = self._read_if_exists(self.project_root / "SAC.md")
        if rules:
            sections.append("## Project Rules\n\n" + rules)

        return redact_secrets("\n\n".join(section.strip() for section in sections if section.strip()))

    def read_task_notes(self, task_id: str) -> str:
        """Return redacted per-task memory."""
        path = self._task_memory_path(task_id)
        if not path.exists():
            return ""
        return redact_secrets(path.read_text(encoding="utf-8"))

    def add_note(self, text: str, task_id: str | None = None) -> Path:
        """Append a non-secret note to project or task memory."""
        self._reject_sensitive(text)
        path = self._task_memory_path(task_id) if task_id else self.project_path
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        separator = "\n\n" if existing.strip() else ""
        path.write_text(existing + separator + text.strip() + "\n", encoding="utf-8")
        return path

    def read_recent_failures(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Read redacted recent failure entries, newest first."""
        entries = self._read_jsonl(self.recent_failures_path)
        result = list(reversed(entries))
        if limit is not None:
            result = result[:limit]
        return [self._redact_obj(item) for item in result]

    def record_failure(
        self,
        *,
        task_id: str | None,
        command: str,
        exit_code: int,
        tail: str,
        suite: str | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Append a redacted bounded failure entry and cap the store."""
        self._reject_sensitive(command)
        redacted_tail = redact_secrets(tail)[-_MAX_TAIL_CHARS:]
        entry = RecentFailureEntry(
            task_id=task_id,
            command=redact_secrets(command),
            suite=redact_secrets(suite) if suite else None,
            exit_code=int(exit_code),
            tail_hash=hashlib.sha256(redacted_tail.encode("utf-8")).hexdigest(),
            tail_summary=redacted_tail,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        ).to_dict()
        self._append_jsonl_capped(self.recent_failures_path, entry)
        return entry

    def read_recent_edits(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Read redacted recent edit entries, newest first."""
        entries = self._read_jsonl(self.recent_edits_path)
        result = list(reversed(entries))
        if limit is not None:
            result = result[:limit]
        return [self._redact_obj(item) for item in result]

    def record_edit(self, entry: dict[str, Any]) -> None:
        """Append a redacted recent edit entry and cap the store."""
        redacted = self._redact_obj(entry)
        self._reject_sensitive(json.dumps(redacted, sort_keys=True, ensure_ascii=False))
        self._append_jsonl_capped(self.recent_edits_path, redacted)

    def read_pinned_files(self) -> list[str]:
        """Read deterministic pinned relative paths."""
        if not self.pinned_path.exists():
            return []
        pins = {line.strip() for line in self.pinned_path.read_text(encoding="utf-8").splitlines() if line.strip()}
        return sorted(pins)

    def pin_file(self, path: str | Path) -> str:
        """Pin a path after normalizing it under project_root."""
        normalized = self.normalize_project_path(path)
        pins = set(self.read_pinned_files())
        pins.add(normalized)
        self._write_pins(pins)
        return normalized

    def unpin_file(self, path: str | Path) -> str:
        """Unpin a normalized path. Missing pins are harmless."""
        normalized = self.normalize_project_path(path)
        pins = set(self.read_pinned_files())
        pins.discard(normalized)
        self._write_pins(pins)
        return normalized

    def clear(self, scope: str, task_id: str | None = None) -> None:
        """Clear one memory scope."""
        if scope == "project":
            self.project_path.unlink(missing_ok=True)
        elif scope == "task":
            if not task_id:
                raise ValueError("--task-id is required for task memory.")
            self._task_memory_path(task_id).unlink(missing_ok=True)
        elif scope == "recent-failures":
            self.recent_failures_path.unlink(missing_ok=True)
        elif scope == "recent-edits":
            self.recent_edits_path.unlink(missing_ok=True)
        elif scope == "pinned":
            self.pinned_path.unlink(missing_ok=True)
        else:
            raise ValueError(f"Unsupported memory scope: {scope}")

    def normalize_project_path(self, path: str | Path) -> str:
        """Normalize a project-relative path and refuse project root escapes."""
        candidate = Path(path)
        absolute = candidate if candidate.is_absolute() else self.project_root / candidate
        resolved = absolute.resolve(strict=False)
        try:
            relative = resolved.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError("Pinned path must stay inside the project root.") from exc
        if not relative.parts:
            raise ValueError("Pinned path must name a file inside the project root.")
        return relative.as_posix()

    def _task_memory_path(self, task_id: str | None) -> Path:
        if not task_id or "/" in task_id or "\\" in task_id or task_id in {".", ".."} or ".." in Path(task_id).parts:
            raise ValueError("Invalid task id.")
        return self.sac_dir / "tasks" / task_id / "memory.md"

    def _write_pins(self, pins: set[str]) -> None:
        self.pinned_path.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(f"{pin}\n" for pin in sorted(pins))
        self.pinned_path.write_text(text, encoding="utf-8")

    def _append_jsonl_capped(self, path: Path, entry: dict[str, Any]) -> None:
        entries = self._read_jsonl(path)
        entries.append(entry)
        entries = entries[-_MAX_RECENT_ENTRIES:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in entries), encoding="utf-8")

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                entries.append(value)
        return entries[-_MAX_RECENT_ENTRIES:]

    def _read_legacy_memory_json(self) -> dict[str, str]:
        path = self.sac_dir / "memory.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(key): str(value) for key, value in data.items()}

    def _read_if_exists(self, path: Path) -> str:
        if not path.exists() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def _redact_obj(self, value: Any) -> Any:
        if isinstance(value, str):
            return redact_secrets(value)
        if isinstance(value, list):
            return [self._redact_obj(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._redact_obj(item) for key, item in value.items()}
        return value

    def _reject_sensitive(self, text: str) -> None:
        lowered = text.lower()
        if any(word in lowered for word in _SENSITIVE_WORDS) or redact_secrets(text) != text:
            raise ValueError("Refusing to store a value that looks sensitive.")
