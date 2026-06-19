"""Governed long-term memory models (v2.4.6)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryFactStatus = Literal["active", "revoked", "expired"]


class MemoryFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    fact_id: str
    content: str
    provenance: str
    approver: str
    admitted_at: str
    expires_at: str | None = None
    revoked_at: str | None = None
    status: MemoryFactStatus = "active"
    permission_scope: list[str] = Field(default_factory=lambda: ["org", "appsec"])
