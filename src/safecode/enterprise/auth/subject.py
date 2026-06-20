"""Map validated OIDC claims into RBACSubject (v2.1.6-T2).

将已通过密码学校验的 OIDC 声明映射为 RBACSubject。
tenant_id 为必填；角色从未知字符串回退为 viewer（偏保守）。
映射结果供 RBAC 与 RAG 权限过滤使用，本身不构成执行授权。
"""

from __future__ import annotations

from safecode.enterprise.auth.oidc import TokenClaims
from safecode.enterprise.rbac.models import DEFAULT_SCOPES_BY_ROLE, ROLE_RANK, RBACSubject, Role
from safecode.enterprise.tenancy import validate_tenant_id

TENANT_CLAIM = "tenant_id"  # 租户标识，多租户隔离边界
ROLE_CLAIM = "roles"  # 多角色声明（数组）
SINGLE_ROLE_CLAIM = "role"  # 单角色声明（字符串）


class SubjectMappingError(Exception):
    """Raised when validated claims cannot be mapped to an RBAC subject."""


def _coerce_role(value: str) -> Role:
    """将声明中的角色字符串转为 Role；未知值回退 viewer（保守默认）。

    潜在问题：IdP 拼写错误的角色会静默降为 viewer，可能导致意外拒绝或权限不足。
    """
    try:
        return Role(value)
    except ValueError:
        return Role.viewer


def _extract_tenant_id(claims: TokenClaims) -> str | None:
    tenant = claims.tenant_id
    if tenant is None and isinstance(claims.model_extra, dict):
        tenant = claims.model_extra.get(TENANT_CLAIM)
    if tenant is None:
        return None
    normalized = str(tenant).strip()
    return normalized or None


def _extract_roles(claims: TokenClaims) -> tuple[Role, ...]:
    raw_roles: list[str] = []
    if claims.roles:
        raw_roles.extend(str(item) for item in claims.roles)
    elif claims.role:
        raw_roles.append(str(claims.role))
    elif isinstance(claims.model_extra, dict):
        extra_roles = claims.model_extra.get(ROLE_CLAIM)
        if isinstance(extra_roles, (list, tuple)):
            raw_roles.extend(str(item) for item in extra_roles)
        extra_role = claims.model_extra.get(SINGLE_ROLE_CLAIM)
        if isinstance(extra_role, str):
            raw_roles.append(extra_role)
    if not raw_roles:
        return (Role.viewer,)
    return tuple(_coerce_role(item) for item in raw_roles)


def map_claims_to_subject(claims: TokenClaims) -> RBACSubject:
    """将校验后的 TokenClaims 映射为 RBACSubject。

    取最高角色决定 permission_scopes；多角色并存时 scopes 仅按 primary_role 选取。
    潜在问题：多角色主体的 scopes 未合并所有角色的范围，可能偏窄。
    """
    tenant_id = _extract_tenant_id(claims)
    if tenant_id is None:
        raise SubjectMappingError("tenant_id claim is required")
    try:
        tenant_id = validate_tenant_id(tenant_id)
    except ValueError as exc:
        raise SubjectMappingError("tenant_id claim is invalid") from exc
    roles = _extract_roles(claims)
    primary_role = max(roles, key=lambda role: ROLE_RANK[role])
    scopes = DEFAULT_SCOPES_BY_ROLE.get(primary_role, ["org"])
    return RBACSubject(
        actor_id=claims.sub,
        tenant_id=tenant_id,
        roles=roles,
        permission_scopes=tuple(scopes),
        metadata={"auth": "oidc"},
    )
