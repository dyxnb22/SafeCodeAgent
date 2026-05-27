"""Time helpers."""

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return a UTC ISO timestamp suitable for metadata and JSONL logs."""
    return datetime.now(timezone.utc).isoformat()
