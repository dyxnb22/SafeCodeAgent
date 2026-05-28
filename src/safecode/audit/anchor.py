"""External audit anchors for detecting full project-log rewrites."""

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from safecode.utils.time import utc_now_iso


@dataclass(frozen=True)
class AuditAnchor:
    """Latest trusted pointer for one project audit log."""

    project_root: str
    log_file: str
    line_count: int
    event_hash: str
    anchored_at: str


class AuditAnchorStore:
    """Store audit anchors outside the project workspace."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.path = self._anchor_dir() / f"{self._project_key()}.jsonl"

    def write(self, log_file: Path, line_count: int, event_hash: str | None) -> None:
        """Append the latest audit log head to a user-level anchor file."""
        if not event_hash:
            return
        anchor = AuditAnchor(
            project_root=str(self.project_root),
            log_file=str(log_file.resolve()),
            line_count=line_count,
            event_hash=event_hash,
            anchored_at=utc_now_iso(),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(anchor.__dict__, ensure_ascii=False, sort_keys=True) + "\n")

    def latest(self, log_file: Path) -> AuditAnchor | None:
        """Return the latest anchor for a log file."""
        if not self.path.exists():
            return None
        log_file_text = str(log_file.resolve())
        latest_anchor: AuditAnchor | None = None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            anchor = AuditAnchor(**json.loads(line))
            if anchor.log_file == log_file_text:
                latest_anchor = anchor
        return latest_anchor

    def _anchor_dir(self) -> Path:
        """Return the user-level anchor directory."""
        env_path = os.getenv("SAFECODE_AUDIT_ANCHOR_DIR")
        if env_path:
            return Path(env_path).expanduser()
        return Path.home() / ".safecode" / "audit-anchors"

    def _project_key(self) -> str:
        """Create a stable filename for the project path."""
        return hashlib.sha256(str(self.project_root).encode("utf-8")).hexdigest()
