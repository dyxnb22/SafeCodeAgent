"""Session-level token and cost accounting (v5.8.0: cost guardrails)."""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float | None = None  # None when pricing is unknown
    cache_read_tokens: int = 0      # v5.1.0: Anthropic prompt-cache read hits
    cache_creation_tokens: int = 0  # v5.1.0: Anthropic prompt-cache writes

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost_usd=None,  # pricing aggregation deferred
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
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
                cache_read_tokens=int(data.get("cache_read_tokens", 0)),
                cache_creation_tokens=int(data.get("cache_creation_tokens", 0)),
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


# ---------------------------------------------------------------------------
# v5.8.0: Budget checking
# ---------------------------------------------------------------------------


@dataclass
class BudgetCheckResult:
    """Result of a budget cap check (v5.8.0)."""

    status: str  # "ok", "warning_90pct", "cap_hit"
    current_tokens: int
    cap: int | None
    message: str = ""


def check_budget(
    usage: TokenUsage,
    cap: int | None,
    *,
    extension_active: bool = False,
) -> BudgetCheckResult:
    """Check session token usage against the per-session cap.

    Returns:
    - ``status="ok"`` when usage is below 90% of cap (or cap is None).
    - ``status="warning_90pct"`` when usage >= 90% of cap.
    - ``status="cap_hit"`` when usage >= 100% of cap.

    When ``extension_active=True``, the effective cap is raised by 10%
    (the user chose to continue after a previous cap_hit).
    """
    if cap is None:
        return BudgetCheckResult(status="ok", current_tokens=usage.total_tokens, cap=None)

    effective_cap = int(cap * 1.1) if extension_active else cap
    pct = usage.total_tokens / effective_cap * 100 if effective_cap > 0 else 0

    if usage.total_tokens >= effective_cap:
        return BudgetCheckResult(
            status="cap_hit",
            current_tokens=usage.total_tokens,
            cap=effective_cap,
            message=(
                f"Session token budget exceeded "
                f"({usage.total_tokens}/{effective_cap} tokens). "
                f"Type 'continue' to extend by 10% or 'stop' to end."
            ),
        )
    if pct >= 90:
        return BudgetCheckResult(
            status="warning_90pct",
            current_tokens=usage.total_tokens,
            cap=effective_cap,
            message=(
                f"Warning: {pct:.0f}% of session token budget used "
                f"({usage.total_tokens}/{effective_cap} tokens)."
            ),
        )
    return BudgetCheckResult(status="ok", current_tokens=usage.total_tokens, cap=effective_cap)


def check_cost_fallback(
    usage: TokenUsage,
    fallback_usd: float | None,
) -> bool:
    """Return True when estimated session cost exceeds the fallback threshold."""
    if fallback_usd is None:
        return False
    if usage.cost_usd is None:
        return False
    return usage.cost_usd >= fallback_usd


def render_budget_summary(usage: TokenUsage, cap: int | None) -> str:
    """Render a human-readable budget summary for /budget shell command.

    Example output::

        Session token usage: 1,200 / 20,000 (6%)
        Estimated cost: $0.06
    """
    cap_str = f"{cap:,}" if cap is not None else "unlimited"
    pct = f" ({usage.total_tokens / cap * 100:.0f}%)" if cap and cap > 0 else ""
    cost_str = f"${usage.cost_usd:.4f}" if usage.cost_usd is not None else "unknown"
    return (
        f"Session token usage: {usage.total_tokens:,} / {cap_str}{pct}\n"
        f"Estimated cost: {cost_str}"
    )
