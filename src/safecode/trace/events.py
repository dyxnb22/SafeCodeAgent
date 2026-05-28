"""Trace event logging for task reconstruction."""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from uuid import uuid4

from safecode.utils.time import utc_now_iso


@dataclass(frozen=True)
class TraceEvent:
    """One trace event."""

    trace_id: str
    span: str
    message: str
    timestamp: str


class TraceLogger:
    """Append trace events to .sac/logs/traces.jsonl."""

    def __init__(self, project_root: Path) -> None:
        self.path = project_root / ".sac" / "logs" / "traces.jsonl"

    def new_trace_id(self) -> str:
        """Create a short trace id."""
        return uuid4().hex[:12]

    def write(self, trace_id: str, span: str, message: str) -> TraceEvent:
        """Append a trace event."""
        event = TraceEvent(trace_id=trace_id, span=span, message=message, timestamp=utc_now_iso())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        return event
