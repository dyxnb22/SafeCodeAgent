"""FastAPI dependency injection for the Team Server (v2.1.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from safecode.enterprise.api.exceptions import TeamServerDependencyError
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.rbac.models import RBACSubject


from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.persistence.postgres.backend import PostgresBackend

PersistenceBackend = LocalBackend | PostgresBackend


SubjectResolver = Callable[[], RBACSubject]


class AuthenticationRequiredError(Exception):
    """Raised when server mode requires an authenticated subject."""


def build_local_backend(sac_root: Path) -> LocalBackend:
    return LocalBackend(sac_root)


def build_postgres_backend(dsn: str, artifacts_root: Path) -> PostgresBackend:
    return PostgresBackend.connect(dsn, artifacts_root)


def build_backend(settings: TeamServerSettings, *, sac_root: Path) -> PersistenceBackend:
    if settings.runtime_mode is RuntimeMode.SERVER:
        if settings.database_url is None:
            raise AuthenticationRequiredError("server mode requires database_url")
        return build_postgres_backend(settings.database_url.get_secret_value(), sac_root)
    return build_local_backend(sac_root)


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
