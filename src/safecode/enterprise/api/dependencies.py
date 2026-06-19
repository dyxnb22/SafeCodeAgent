"""FastAPI dependency injection for the Team Server (v2.1.4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from safecode.enterprise.api.exceptions import SettingsValidationError, TeamServerDependencyError
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.auth.oidc import OidcValidator, TokenValidationError, build_oidc_validator
from safecode.enterprise.auth.subject import SubjectMappingError, map_claims_to_subject
from safecode.enterprise.rbac.models import RBACSubject


from safecode.enterprise.persistence.local_backend import LocalBackend

PersistenceBackend = Any


SubjectResolver = Callable[[], RBACSubject]


class AuthenticationRequiredError(Exception):
    """Raised when server mode requires an authenticated subject."""


def build_local_backend(sac_root: Path) -> LocalBackend:
    return LocalBackend(sac_root)


def build_postgres_backend(dsn: str, artifacts_root: Path) -> Any:
    from safecode.enterprise.persistence.postgres.backend import PostgresBackend

    return PostgresBackend.connect(dsn, artifacts_root)


def build_backend(settings: TeamServerSettings, *, sac_root: Path) -> PersistenceBackend:
    if settings.runtime_mode is RuntimeMode.SERVER:
        if settings.database_url is None:
            raise AuthenticationRequiredError("server mode requires database_url")
        return build_postgres_backend(settings.database_url.get_secret_value(), sac_root)
    return build_local_backend(sac_root)


def resolve_bearer_subject(
    authorization_header: str | None,
    *,
    oidc_validator: OidcValidator,
) -> RBACSubject:
    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise AuthenticationRequiredError("bearer token required")
    token = authorization_header.removeprefix("Bearer ").strip()
    if not token:
        raise AuthenticationRequiredError("bearer token required")
    try:
        claims = oidc_validator.validate_token(token)
        return map_claims_to_subject(claims)
    except (TokenValidationError, SubjectMappingError) as exc:
        raise AuthenticationRequiredError(str(exc)) from exc


def build_local_subject_resolver(settings: TeamServerSettings) -> SubjectResolver:
    def _resolve() -> RBACSubject:
        actor = settings.operator_actor
        if not actor:
            raise AuthenticationRequiredError("operator_actor required in local mode")
        return RBACSubject(actor_id=actor, tenant_id="local")

    return _resolve


def fail_closed_subject_resolver(settings: TeamServerSettings) -> SubjectResolver:
    """Reject unauthenticated access in server mode until v2.1.6 OIDC wiring."""

    def _resolve() -> RBACSubject:
        if settings.runtime_mode is RuntimeMode.SERVER:
            raise AuthenticationRequiredError("authenticated subject required")
        actor = settings.operator_actor
        if not actor:
            raise AuthenticationRequiredError("operator_actor required in local mode")
        return RBACSubject(actor_id=actor, tenant_id="local")

    return _resolve


def build_oidc_validator_from_settings(settings: TeamServerSettings) -> OidcValidator:
    if not settings.oidc_issuer or not settings.oidc_audience:
        raise SettingsValidationError("server mode requires oidc_issuer and oidc_audience")
    if not settings.oidc_jwks_path:
        raise SettingsValidationError("server mode requires oidc_jwks_path until discovery fetch is wired")
    jwks_path = Path(settings.oidc_jwks_path)
    if not jwks_path.is_file():
        raise SettingsValidationError(f"oidc jwks file not found: {jwks_path}")
    jwks = json.loads(jwks_path.read_text(encoding="utf-8"))
    return build_oidc_validator(
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
        jwks=jwks,
    )


def resolve_subject(
    resolver: SubjectResolver,
) -> RBACSubject:
    return resolver()


def import_fastapi():
    try:
        from fastapi import FastAPI
    except ImportError as exc:
        raise TeamServerDependencyError(
            "team-server optional extra is required for FastAPI; install safecode-agent[team-server]"
        ) from exc
    return FastAPI
