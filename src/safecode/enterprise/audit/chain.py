"""Enterprise audit hash-chain wrapper around the legacy logger."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.enterprise.audit.events import AuditEventKind


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class EnterpriseAuditChain:
    """Write enterprise taxonomy events through the legacy hash-chain logger."""

    def __init__(self, project_root: Path, *, chain_id: str = "enterprise") -> None:
        self.project_root = project_root
        self.chain_id = chain_id
        self._logger = AuditLogger(project_root)

    @property
    def log_file(self) -> Path:
        return self._logger.log_file

    def emit(
        self,
        kind: AuditEventKind,
        *,
        run_id: str,
        actor_id: str,
        payload: dict[str, str] | None = None,
        status: str = "success",
        message: str | None = None,
    ) -> AuditEvent:
        metadata = {"run_id": run_id, "chain_id": self.chain_id}
        if payload:
            metadata.update({key: str(value) for key, value in payload.items()})
        event = AuditEvent(
            type=kind.value,
            timestamp=_utc_now(),
            status=status,
            message=message,
            metadata=metadata,
            trace_id=run_id,
        )
        self._logger.write(event, task_id=run_id)
        return event

    def verify_integrity(self) -> tuple[bool, str]:
        return self._logger.verify_integrity()

    def iter_events(self) -> list[AuditEvent]:
        return self._logger.iter_events()
