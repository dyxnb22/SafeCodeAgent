"""RBAC subject and role models."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from safecode.enterprise.policy.resolver import load_org_layer, load_user_layer


class Role(str, Enum):
    viewer = "viewer"
    developer = "developer"
    security_reviewer = "security_reviewer"
    maintainer = "maintainer"
    platform_admin = "platform_admin"


ROLE_RANK: dict[Role, int] = {
    Role.viewer: 0,
    Role.developer: 1,
    Role.security_reviewer: 2,
    Role.maintainer: 3,
    Role.platform_admin: 4,
}


DEFAULT_SCOPES_BY_ROLE: dict[Role, list[str]] = {
    Role.viewer: ["org"],
    Role.developer: ["org", "project"],
    Role.security_reviewer: ["org", "project", "security"],
    Role.maintainer: ["org", "project", "security", "maintain"],
    Role.platform_admin: ["org", "project", "security", "maintain", "admin"],
}


class RBACSubject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: str
    tenant_id: str = "local"
    roles: tuple[Role, ...] = (Role.developer,)
    permission_scopes: tuple[str, ...] = ("org",)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("roles", mode="before")
    @classmethod
    def _coerce_roles(cls, value: Any) -> tuple[Role, ...]:
        if value is None:
            return (Role.developer,)
        if isinstance(value, Role):
            return (value,)
        if isinstance(value, str):
            return (Role(value),)
        return tuple(Role(item) if isinstance(item, str) else item for item in value)

    @field_validator("permission_scopes", mode="before")
    @classmethod
    def _coerce_scopes(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ("org",)
        return tuple(value)

    def highest_role(self) -> Role:
        return max(self.roles, key=lambda role: ROLE_RANK[role])


def _role_from_user_policy(config_root: Path | None) -> Role:
    layer = load_user_layer(config_root)
    role_value = layer.values.get("role")
    if role_value is None:
        return Role.developer
    try:
        return Role(str(role_value.value))
    except ValueError:
        return Role.developer


def resolve_subject(
    actor_id: str,
    *,
    config_root: Path | None = None,
    as_role: Role | str | None = None,
    tenant_id: str = "local",
) -> RBACSubject:
    org_layer = load_org_layer(config_root)
    allow_flag = org_layer.values.get("allow_as_role_flag")
    allow_as_role = str(allow_flag.value).strip().lower() in {"1", "true", "yes", "on"} if allow_flag else False
    role = _role_from_user_policy(config_root)
    if as_role is not None:
        if not allow_as_role:
            raise PermissionError("--as-role is blocked unless org policy allow_as_role_flag=true")
        role = Role(as_role) if isinstance(as_role, str) else as_role
    scopes = DEFAULT_SCOPES_BY_ROLE.get(role, ["org"])
    return RBACSubject(
        actor_id=actor_id,
        tenant_id=tenant_id,
        roles=(role,),
        permission_scopes=tuple(scopes),
    )


def load_user_role_from_file(path: Path) -> Role:
    if not path.is_file():
        return Role.developer
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return Role.developer
    policies = payload.get("policies", payload)
    if not isinstance(policies, dict):
        return Role.developer
    role_value = policies.get("role", "developer")
    try:
        return Role(str(role_value))
    except ValueError:
        return Role.developer
