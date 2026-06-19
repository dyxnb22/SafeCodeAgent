"""Enterprise policy layer models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ApprovalTier = Literal["AUTO", "CONFIRM", "GATE", "BLOCK"]
PolicyLayerName = Literal["org", "user", "project", "env", "workflow"]

TIER_STRICTNESS: dict[str, int] = {
    "AUTO": 0,
    "CONFIRM": 1,
    "GATE": 2,
    "BLOCK": 3,
}

POLICY_KEY_ALIASES: dict[str, str] = {
    "github_write": "github_write_comment",
}


class PolicyValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    value: ApprovalTier | str
    rationale: str | None = None


class PolicyLayer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: PolicyLayerName
    source_ref: str
    values: dict[str, PolicyValue] = Field(default_factory=dict)


class PolicyOverrideBlocked(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    attempted_value: str
    final_value: str
    layer: PolicyLayerName


class PolicySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: str
    tenant_id: str = "local"
    layers: tuple[PolicyLayer, ...]
    merged: dict[str, PolicyValue]
    created_at: str
    blocked_overrides: tuple[PolicyOverrideBlocked, ...] = Field(default_factory=tuple)


def normalize_policy_key(key: str) -> str:
    return POLICY_KEY_ALIASES.get(key, key)


def is_approval_tier(value: str) -> bool:
    return value in TIER_STRICTNESS


def max_tier(*values: ApprovalTier) -> ApprovalTier:
    return max(values, key=lambda item: TIER_STRICTNESS[item])


def is_weakening(current: ApprovalTier, attempted: ApprovalTier) -> bool:
    return TIER_STRICTNESS[attempted] < TIER_STRICTNESS[current]
