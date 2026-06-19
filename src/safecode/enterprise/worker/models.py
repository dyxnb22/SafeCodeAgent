"""Worker queue and command models (v2.1.5)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RunCommandKind = Literal["start", "resume", "cancel"]
QueueJobStatus = Literal["pending", "completed", "failed"]


class RunAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    status: str
    status_url: str


class RunCommandRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str
    idempotency_key: str
    command: RunCommandKind
    run_id: str
    payload: dict[str, str] = Field(default_factory=dict)
    created_at: str


class QueueJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    tenant_id: str
    run_id: str
    command: RunCommandKind
    status: QueueJobStatus
    payload: dict[str, str] = Field(default_factory=dict)
    created_at: str
