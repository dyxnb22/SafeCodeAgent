"""Append-only JSONL audit logger."""

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from safecode.audit.anchor import AuditAnchorStore
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig


class AuditLogger:
    """Write auditable project events."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.log_file = self.project_root / self.config.sac_dir / "logs" / "events.jsonl"
        self.anchor_store = AuditAnchorStore(project_root)

    def write(self, event: AuditEvent) -> None:
        """Append one event to .sac/logs/events.jsonl."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        previous_hash = self._last_hash()
        event.previous_hash = previous_hash
        event.event_hash = self._hash_event(event)
        line = json.dumps(event.model_dump(), ensure_ascii=False, sort_keys=True)
        with self.log_file.open("a", encoding="utf-8") as file:
            file.write(line + "\n")
        self.anchor_store.write(self.log_file, self._line_count(), event.event_hash)

    def read_recent(self, limit: int = 20) -> list[AuditEvent]:
        """Read recent events for sac history."""
        if not self.log_file.exists():
            return []

        lines = self.log_file.read_text(encoding="utf-8").splitlines()
        recent_lines = lines[-limit:]
        return [AuditEvent(**json.loads(line)) for line in recent_lines if line.strip()]

    def verify_integrity(self) -> tuple[bool, str]:
        """Verify the audit hash chain."""
        if not self.log_file.exists():
            return True, "No audit log found."

        previous_hash: str | None = None
        line_count = 0
        for line_number, line in enumerate(self.log_file.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            line_count += 1
            try:
                event = AuditEvent(**json.loads(line))
            except (json.JSONDecodeError, ValidationError) as exc:
                return False, f"Audit log parse error at line {line_number}: {exc}"
            if not event.event_hash:
                return False, f"Legacy audit event without hash at line {line_number}."
            if event.previous_hash != previous_hash:
                return False, f"Audit hash chain break at line {line_number}."
            expected_hash = self._hash_event(event)
            if event.event_hash != expected_hash:
                return False, f"Audit event hash mismatch at line {line_number}."
            previous_hash = event.event_hash
        anchor = self.anchor_store.latest(self.log_file)
        if anchor:
            if anchor.line_count != line_count or anchor.event_hash != previous_hash:
                return False, "Audit anchor mismatch; the log may have been rewritten."
            return True, "Audit log integrity verified with external anchor."
        return True, "Audit log integrity verified."

    def _last_hash(self) -> str | None:
        """Return the latest event hash."""
        if not self.log_file.exists():
            return None
        for line in reversed(self.log_file.read_text(encoding="utf-8").splitlines()):
            if line.strip():
                return AuditEvent(**json.loads(line)).event_hash
        return None

    def _line_count(self) -> int:
        """Count non-empty audit events."""
        if not self.log_file.exists():
            return 0
        return sum(1 for line in self.log_file.read_text(encoding="utf-8").splitlines() if line.strip())

    def _hash_event(self, event: AuditEvent) -> str:
        """Hash event content excluding event_hash itself."""
        data = event.model_dump()
        data["event_hash"] = None
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
