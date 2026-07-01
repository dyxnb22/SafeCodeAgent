"""Enterprise policy layer models.

中文模块说明：策略层 Pydantic 模型（PolicySnapshot、PolicyLayer、ApprovalTier 等）。
- 架构位置：``policy/resolver.py`` 的输出类型；workflow 状态携带 snapshot_id。
- 安全不变量：快照绑定审批与执行；层级越高优先级越大；blocked_override 记录弱化企图。
- 学习路径：先读本文件字段，再读 ``resolver.py`` 与 ``test_resolver_precedence.py``。
"""

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
