"""Human checkpoint prompts for approval-gated actions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.utils.time import utc_now_iso


@dataclass(frozen=True)
class HumanCheckpoint:
    """A standardized user checkpoint before a sensitive action."""

    checkpoint_type: str
    title: str
    prompt: str
    risk_level: str
    summary: str
    subject_hash: str
    metadata: dict[str, str] = field(default_factory=dict)


class HumanCheckpointPresenter:
    """Create and audit human checkpoints without approving actions."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.audit_logger = AuditLogger(project_root, self.config)

    def checkpoint(
        self,
        checkpoint_type: str,
        title: str,
        prompt: str,
        risk_level: str,
        summary: str,
        subject: str,
        metadata: dict[str, str] | None = None,
    ) -> HumanCheckpoint:
        """Create and audit a standardized checkpoint."""
        checkpoint = HumanCheckpoint(
            checkpoint_type=checkpoint_type,
            title=title,
            prompt=prompt,
            risk_level=risk_level,
            summary=summary,
            subject_hash=self._hash_subject(subject),
            metadata=dict(metadata or {}),
        )
        self.audit_logger.write(
            AuditEvent(
                type="human_checkpoint_presented",
                timestamp=utc_now_iso(),
                status="blocked",
                message=checkpoint.summary,
                metadata={
                    "checkpoint_type": checkpoint.checkpoint_type,
                    "risk_level": checkpoint.risk_level,
                    "subject_hash": checkpoint.subject_hash,
                    **checkpoint.metadata,
                },
            )
        )
        return checkpoint

    @staticmethod
    def _hash_subject(subject: str) -> str:
        return hashlib.sha256(subject.encode("utf-8")).hexdigest()[:16]
