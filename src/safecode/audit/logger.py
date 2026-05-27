"""Append-only JSONL audit logger."""

import json
from pathlib import Path

from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig


class AuditLogger:
    """Write auditable project events."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig()
        self.log_file = self.project_root / self.config.sac_dir / "logs" / "events.jsonl"

    def write(self, event: AuditEvent) -> None:
        """Append one event to .sac/logs/events.jsonl."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.model_dump(), ensure_ascii=False)
        with self.log_file.open("a", encoding="utf-8") as file:
            file.write(line + "\n")

    def read_recent(self, limit: int = 20) -> list[AuditEvent]:
        """Read recent events for sac history."""
        if not self.log_file.exists():
            return []

        lines = self.log_file.read_text(encoding="utf-8").splitlines()
        recent_lines = lines[-limit:]
        return [AuditEvent(**json.loads(line)) for line in recent_lines if line.strip()]
