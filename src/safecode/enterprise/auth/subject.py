"""Map validated OIDC claims into RBACSubject (v2.1.6-T2)."""

from __future__ import annotations

from safecode.enterprise.auth.oidc import TokenClaims
from safecode.enterprise.rbac.models import DEFAULT_SCOPES_BY_ROLE, ROLE_RANK, RBACSubject, Role

TENANT_CLAIM = "tenant_id"
ROLE_CLAIM = "roles"
SINGLE_ROLE_CLAIM = "role"


class SubjectMappingError(Exception):
    """Raised when validated claims cannot be mapped to an RBAC subject."""


def _coerce_role(value: str) -> Role:
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
    tenant_id = _extract_tenant_id(claims)
    if tenant_id is None:
        raise SubjectMappingError("tenant_id claim is required")
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
