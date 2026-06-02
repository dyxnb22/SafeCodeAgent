"""Session-level token and cost accounting."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float | None = None  # None when pricing is unknown

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost_usd=None,  # pricing aggregation deferred
        )

    def as_dict(self) -> dict:
        return asdict(self)


class SessionCostAccumulator:
    """Persist and accumulate token usage for one session.

    Cost JSON stored at .sac/sessions/<session_id>/cost.json.
    """

    def __init__(self, sac_dir: Path, session_id: str) -> None:
        self._path = sac_dir / "sessions" / session_id / "cost.json"
        self._session_id = session_id

    def record(self, usage: TokenUsage) -> None:
        """Accumulate usage into the persisted cost.json atomically."""
        current = self.load() or TokenUsage()
        updated = current + usage
        self._atomic_write(updated)

    def total(self) -> TokenUsage:
        """Return the accumulated total, or a zero-value if no file."""
        return self.load() or TokenUsage()

    def load(self) -> TokenUsage | None:
        """Return the persisted usage, or None if no file exists."""
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return TokenUsage(
                prompt_tokens=int(data.get("prompt_tokens", 0)),
                completion_tokens=int(data.get("completion_tokens", 0)),
                total_tokens=int(data.get("total_tokens", 0)),
                cost_usd=data.get("cost_usd"),
            )
        except (json.JSONDecodeError, OSError, ValueError):
            return None

    def _atomic_write(self, usage: TokenUsage) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(f".{self._path.name}.{uuid4().hex}.tmp")
        try:
            tmp.write_text(json.dumps(usage.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(tmp, self._path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
