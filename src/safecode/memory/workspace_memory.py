"""Cross-session workspace memory store (v6.30).

WorkspaceMemoryStore records what the agent learns from each session so that
future sessions can benefit without repeating the same discovery work.

Key behaviours:
- Append-only JSONL under ``.sac/workspace_memory.jsonl``.
- LRU cap at ``_MAX_ENTRIES`` (150) and ``_MAX_FILE_BYTES`` (300 KB).
- Every entry is redacted before write; secrets never land on disk.
- ``ContextCollector`` loads the most recent relevant entries and injects them
  as a ``workspace_memory`` context block at prompt time.

Entry sources:
- ``agent_observed``: automatically captured after successful apply / run_command.
- ``user_stated``: manually pinned via ``sac memory pin`` or equivalent CLI.
- ``inferred``: derived from observing repeated patterns across sessions.
"""
from __future__ import annotations

import json
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safecode.context.redactor import redact_secrets

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_ENTRIES = 150
_MAX_FILE_BYTES = 300_000
_MAX_VALUE_CHARS = 2000
_MAX_KEY_CHARS = 120
_MAX_CONTEXT_ENTRIES = 5
_MAX_CONTEXT_CHARS = 1600

_SENSITIVE_WORDS = frozenset(
    {"token", "secret", "password", "api_key", "apikey", "private_key", "credential"}
)

# Key normalisation: squash runs of punctuation into '-' so that
# ``fix:config.py`` and ``fix->config.py`` both become ``fix-config-py``.
_BAD_KEY_CHARS = re.compile(r"[^a-zA-Z0-9_.\-: ]+")
_SQUASH_SEP = re.compile(r"[:.\- ]{2,}")
_KEY_NORMALISE = re.compile(r"[^a-zA-Z0-9_.\-:]")


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkspaceMemoryEntry:
    """One cross-session observation about this project."""

    key: str
    value: str
    source: str  # "agent_observed" | "user_stated" | "inferred"
    confidence: float  # 0.0 – 1.0
    timestamp: str
    session_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkspaceMemoryEntry":
        return cls(
            key=str(data.get("key", "")),
            value=str(data.get("value", "")),
            source=str(data.get("source", "agent_observed")),
            confidence=float(data.get("confidence", 0.5)),
            timestamp=str(data.get("timestamp", "")),
            session_id=str(data.get("session_id", "")),
        )

    @property
    def age_score(self) -> float:
        """Heuristic: newer = higher score. Returns a value in [0, 1]."""
        try:
            ts = datetime.fromisoformat(self.timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
            return max(0.0, 1.0 - age_hours / (24 * 30))  # decay over ~30 days
        except Exception:
            return 0.5

    def to_context_line(self) -> str:
        """One compact line for the context block."""
        return (
            f"- [{self.key}] {self.value[:200]}"
            f"  (source={self.source}, conf={self.confidence:.2f})"
        )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class WorkspaceMemoryStore:
    """Cross-session workspace memory under `.sac/workspace_memory.jsonl`.

    Usage::

        store = WorkspaceMemoryStore(project_root)
        store.record("test_command", "python -m pytest -q", source="agent_observed")
        store.record("fix:config", "parse_config returns {} for None input")

        # In ContextCollector.collect():
        context["workspace_memory"] = store.top_context_block()
    """

    def __init__(self, project_root: Path) -> None:
        self.path = project_root / ".sac" / "workspace_memory.jsonl"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(
        self,
        key: str,
        value: str,
        *,
        source: str = "agent_observed",
        session_id: str = "",
        confidence: float = 0.7,
    ) -> WorkspaceMemoryEntry | None:
        """Record one observation. Returns None when the value is too sensitive or empty."""
        key = _normalise_key(key)
        value = redact_secrets(value[:_MAX_VALUE_CHARS])
        if not key or not value or _looks_sensitive(value):
            return None

        entry = WorkspaceMemoryEntry(
            key=key,
            value=value,
            source=source,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
        )

        self._append_and_evict(entry)
        return entry

    def record_many(
        self,
        entries: list[tuple[str, str]],
        *,
        source: str = "agent_observed",
        session_id: str = "",
    ) -> list[WorkspaceMemoryEntry]:
        """Batch-record several entries."""
        results: list[WorkspaceMemoryEntry] = []
        for key, value in entries:
            result = self.record(key, value, source=source, session_id=session_id)
            if result:
                results.append(result)
        return results

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load_all(self) -> list[WorkspaceMemoryEntry]:
        """Load all entries, newest first."""
        entries = []
        for line in _read_jsonl_lines(self.path):
            entry = WorkspaceMemoryEntry.from_dict(line)
            if entry.key and entry.value:
                entries.append(entry)
        # Newest first by timestamp (default insertion order is oldest-first in LRU)
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries

    def top_context_block(self, query: str | None = None, limit: int = _MAX_CONTEXT_ENTRIES) -> str:
        """Return a compact text block for injection into the agent prompt.

        When *query* is provided, entries whose key/value overlaps with the
        query are ranked higher.
        """
        entries = self.load_all()
        if not entries:
            return ""

        entries = self._rank(entries, query)[:limit]
        lines = [f"## Workspace Memory ({len(self)} entries)"]
        chars = len(lines[0])
        for e in entries:
            line = e.to_context_line()
            if chars + len(line) + 2 > _MAX_CONTEXT_CHARS:
                break
            lines.append(line)
            chars += len(line) + 2
        return "\n".join(lines)

    def query(self, keyword: str, limit: int = 5) -> list[WorkspaceMemoryEntry]:
        """Return entries whose key or value contain *keyword* (case-insensitive)."""
        keyword_lower = keyword.lower()
        results = []
        for e in self.load_all():
            if keyword_lower in e.key.lower() or keyword_lower in e.value.lower():
                results.append(e)
                if len(results) >= limit:
                    break
        return results

    def __len__(self) -> int:
        return sum(1 for _ in _read_jsonl_lines(self.path))

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear_stale(self, max_age_days: int = 60) -> int:
        """Remove entries older than *max_age_days*. Returns count of removed entries."""
        cutoff = datetime.now(timezone.utc).isoformat()
        entries = self.load_all()
        kept = []
        removed = 0
        for e in entries:
            if e.timestamp >= cutoff or (datetime.now(timezone.utc) - datetime.fromisoformat(e.timestamp)).days <= max_age_days:
                kept.append(e.to_dict())
            else:
                removed += 1
        if removed:
            _write_jsonl_lines(self.path, kept)
        return removed

    def export_all(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.load_all()]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rank(
        self, entries: list[WorkspaceMemoryEntry], query: str | None
    ) -> list[WorkspaceMemoryEntry]:
        """Score entries by recency + relevance to query, highest first."""

        def _score(e: WorkspaceMemoryEntry) -> float:
            s = e.age_score * e.confidence
            if query:
                q = query.lower()
                if q in e.key.lower():
                    s += 0.5
                elif q in e.value.lower():
                    s += 0.3
                # Boost for high-confidence sources
                if e.source == "user_stated":
                    s += 0.2
            return s

        return sorted(entries, key=_score, reverse=True)

    def _append_and_evict(self, entry: WorkspaceMemoryEntry) -> None:
        entries = _read_jsonl_lines(self.path)
        entries.append(entry.to_dict())
        # LRU eviction: if we're over the entry or byte limit, drop oldest first.
        while len(entries) > _MAX_ENTRIES:
            entries.pop(0)
        total = sum(len(json.dumps(e, sort_keys=True)) + 1 for e in entries)
        while total > _MAX_FILE_BYTES and len(entries) > 10:
            removed = entries.pop(0)
            total = sum(len(json.dumps(e, sort_keys=True)) + 1 for e in entries)
        _write_jsonl_lines(self.path, entries)


# ---------------------------------------------------------------------------
# ContextCollector integration helper
# ---------------------------------------------------------------------------


def inject_workspace_memory(
    context: dict[str, Any],
    project_root: Path,
    query: str | None = None,
) -> dict[str, Any]:
    """Inject workspace memory block into the context dict.

    Safe to call even when the store file is missing or corrupted — returns
    the context unchanged on any error.
    """
    try:
        store = WorkspaceMemoryStore(project_root)
        block = store.top_context_block(query=query)
        if block:
            context["workspace_memory"] = block
    except Exception:
        pass
    return context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_key(raw: str) -> str:
    """Normalise a raw key to a safe, canonical form."""
    key = raw.strip()[: _MAX_KEY_CHARS]
    key = _BAD_KEY_CHARS.sub("-", key)
    key = _SQUASH_SEP.sub("-", key)
    key = _KEY_NORMALISE.sub("", key)
    return key.strip("-:.") if key.strip("-:.") else ""


def _looks_sensitive(text: str) -> bool:
    lowered = text.lower()
    return any(w in lowered for w in _SENSITIVE_WORDS)


def _read_jsonl_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                entries.append(obj)
        except json.JSONDecodeError:
            continue
    return entries


def _write_jsonl_lines(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n"
            for e in entries
        ),
        encoding="utf-8",
    )
