"""ConversationBuffer — persistent, bounded multi-turn conversation history (v6.7.0).

Stores user/assistant/tool messages across shell turns so that
``choose_tool_native()`` receives full conversation history instead of
rebuilding context from scratch on every call.

Safety:
- All content is passed through ``redact_secrets()`` before writing to disk.
- Buffer is capped at ``_MAX_TURNS`` round-trip pairs (user + assistant).
  When the cap is exceeded the oldest ``_COMPRESS_BATCH`` turns are replaced
  with a single compact summary so the context window stays manageable.
- Never raises on read/write failures — all I/O errors return empty state.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from safecode.context.redactor import redact_secrets

_MAX_TURNS = 40          # max user+assistant message pairs kept in buffer
_COMPRESS_BATCH = 10     # how many old pairs to compress at once
_MAX_CONTENT_CHARS = 8000  # per-message content cap before persisting
_FILE_PATH_RE = re.compile(
    r"\b(?:[a-zA-Z0-9_\-]+/)+[a-zA-Z0-9_\-]+\.[a-zA-Z]{1,8}\b"
)


@dataclass
class ConversationBuffer:
    """In-memory + disk-backed conversation buffer for one shell session."""

    session_id: str
    sac_dir: Path
    _messages: list[dict[str, Any]] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, session_id: str, sac_dir: Path) -> "ConversationBuffer":
        """Load from disk, or return an empty buffer if the file is missing/corrupt."""
        buf = cls(session_id=session_id, sac_dir=sac_dir)
        path = buf._path()
        if not path.exists():
            return buf
        try:
            messages = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                msg = json.loads(line)
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    messages.append(msg)
            buf._messages = messages[-(_MAX_TURNS * 2):]
        except Exception:
            pass
        return buf

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append_user(self, content: str) -> None:
        self._append({"role": "user", "content": self._clean(content)})

    def append_assistant(self, content: str) -> None:
        self._append({"role": "assistant", "content": self._clean(content)})

    def append_tool_result(self, tool_name: str, output: str) -> None:
        self._append({
            "role": "tool",
            "content": self._clean(f"[{tool_name}]: {output}"),
        })

    def _append(self, msg: dict[str, Any]) -> None:
        self._messages.append(msg)
        self._maybe_compress()
        self._persist()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def to_messages(self) -> list[dict[str, Any]]:
        """Return current message list (copy), safe to pass to LLM clients."""
        return list(self._messages)

    def mentioned_files(self) -> list[str]:
        """Extract file-path-like strings from all messages (for context bonus)."""
        seen: set[str] = set()
        result: list[str] = []
        for msg in self._messages:
            content = str(msg.get("content", ""))
            for match in _FILE_PATH_RE.findall(content):
                if match not in seen:
                    seen.add(match)
                    result.append(match)
        return result

    def is_empty(self) -> bool:
        return len(self._messages) == 0

    def turn_count(self) -> int:
        """Number of user messages (≈ conversation turns)."""
        return sum(1 for m in self._messages if m.get("role") == "user")

    def compact_now(self) -> None:
        """Manually compact the oldest turns and persist the result."""
        if len(self._messages) <= 1:
            return
        self._compress_oldest_turns(force=True)
        self._persist()

    # ------------------------------------------------------------------
    # Compression
    # ------------------------------------------------------------------

    def _maybe_compress(self) -> None:
        """If buffer exceeds cap, replace oldest COMPRESS_BATCH pairs with a summary."""
        user_count = sum(1 for m in self._messages if m.get("role") == "user")
        if user_count <= _MAX_TURNS:
            return
        self._compress_oldest_turns(force=False)

    def _compress_oldest_turns(self, *, force: bool) -> None:
        # Find the first COMPRESS_BATCH user-message boundaries and slice them out.
        boundary = 0
        users_seen = 0
        for i, msg in enumerate(self._messages):
            if msg.get("role") == "user":
                users_seen += 1
                if users_seen >= _COMPRESS_BATCH:
                    boundary = i + 1
                    break
        if boundary == 0 and force:
            boundary = max(1, len(self._messages) // 2)
        if boundary <= 0:
            return

        old_block = self._messages[:boundary]
        self._messages = self._messages[boundary:]

        # Build a compact summary of the removed block.
        summary_lines = ["[Conversation summary — earlier turns compressed]"]
        for msg in old_block:
            role = msg.get("role", "?")
            snippet = str(msg.get("content", ""))[:200]
            summary_lines.append(f"  {role}: {snippet}")
        summary = "\n".join(summary_lines)

        self._messages.insert(0, {"role": "assistant", "content": summary})

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        try:
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "".join(
                    json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n"
                    for m in self._messages
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _path(self) -> Path:
        return self.sac_dir / "sessions" / self.session_id / "conversation.jsonl"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clean(self, text: str) -> str:
        """Redact secrets and cap length before storing."""
        return redact_secrets(str(text))[:_MAX_CONTENT_CHARS]
