"""Structured runtime logs for debugging failures."""

import json
import traceback
from pathlib import Path

from pydantic import BaseModel, Field

from safecode.config import SafeCodeConfig
from safecode.utils.time import utc_now_iso


class RuntimeLogEvent(BaseModel):
    """One runtime log event written to .sac/logs/runtime.jsonl."""

    timestamp: str
    level: str
    component: str
    message: str
    trace_id: str | None = None
    error_type: str | None = None
    traceback: str | None = None
    details: dict[str, str] = Field(default_factory=dict)


class RuntimeLogger:
    """Append structured runtime logs for operational debugging."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.log_file = self.project_root / self.config.sac_dir / "logs" / "runtime.jsonl"

    def info(self, component: str, message: str, **details: str) -> RuntimeLogEvent:
        """Write an info event."""
        return self.write("info", component, message, details=details)

    def error(
        self,
        component: str,
        message: str,
        exc: BaseException | None = None,
        trace_id: str | None = None,
        **details: str,
    ) -> RuntimeLogEvent:
        """Write an error event, including exception details when available."""
        return self.write(
            "error",
            component,
            message,
            trace_id=trace_id,
            error_type=type(exc).__name__ if exc else None,
            traceback="".join(traceback.format_exception(exc)) if exc else None,
            details=details,
        )

    def write(
        self,
        level: str,
        component: str,
        message: str,
        trace_id: str | None = None,
        error_type: str | None = None,
        traceback: str | None = None,
        details: dict[str, str] | None = None,
    ) -> RuntimeLogEvent:
        """Append one runtime log event."""
        event = RuntimeLogEvent(
            timestamp=utc_now_iso(),
            level=level,
            component=component,
            message=message,
            trace_id=trace_id,
            error_type=error_type,
            traceback=traceback,
            details=details or {},
        )
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
        return event

    def read_recent(self, limit: int = 20, level: str | None = None) -> list[RuntimeLogEvent]:
        """Read recent runtime log events."""
        if not self.log_file.exists():
            return []
        lines = self.log_file.read_text(encoding="utf-8").splitlines()
        events = [RuntimeLogEvent(**json.loads(line)) for line in lines if line.strip()]
        if level:
            events = [event for event in events if event.level == level]
        return events[-limit:]
