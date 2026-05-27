"""Audit event models."""

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """One JSONL event written to .sac/logs/events.jsonl."""

    type: str
    timestamp: str
    status: str = "success"
    patch_id: str | None = None
    checkpoint_id: str | None = None
    files: list[str] = Field(default_factory=list)
    message: str | None = None
    error: str | None = None
