"""Performance budget models and helpers for eval/replay runs.

Tracks lightweight, deterministic telemetry — context size, command
duration, LLM latency placeholder, and disk growth — without adding new
runtime dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PerformanceBudget:
    """Measured performance budget for one replay run.

    All fields have safe zero/None defaults so callers can construct a budget
    incrementally.  ``llm_latency_ms`` is ``None`` when no real LLM was
    invoked (e.g. ``TaskReplayRunner`` never calls an LLM).
    """

    context_size_bytes: int = 0
    total_command_duration_ms: float = 0.0
    llm_latency_ms: float | None = None
    disk_growth_bytes: int = 0

    def as_dict(self) -> dict[str, object]:
        """Return a deterministic, JSON-serializable representation."""
        return {
            "context_size_bytes": self.context_size_bytes,
            "total_command_duration_ms": round(self.total_command_duration_ms, 3),
            "llm_latency_ms": self.llm_latency_ms,
            "disk_growth_bytes": self.disk_growth_bytes,
        }


def compute_context_size(snapshot: dict[str, str]) -> int:
    """Return total UTF-8 byte count across all file contents in *snapshot*."""
    return sum(len(content.encode("utf-8", errors="replace")) for content in snapshot.values())


def compute_disk_growth(before: dict[str, str], after: dict[str, str]) -> int:
    """Return net bytes added to workspace (never negative).

    Computes the difference in total encoded size between *after* and *before*
    snapshots.  Returns 0 when disk usage did not grow.
    """
    before_bytes = sum(len(v.encode("utf-8", errors="replace")) for v in before.values())
    after_bytes = sum(len(v.encode("utf-8", errors="replace")) for v in after.values())
    return max(0, after_bytes - before_bytes)
