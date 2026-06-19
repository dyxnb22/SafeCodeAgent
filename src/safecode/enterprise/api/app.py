"""FastAPI application factory for the Team Server (v2.1.4-T1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from safecode.enterprise.api.contracts import CONTRACT_STATUS
from safecode.enterprise.api.dependencies import (
    AuthenticationRequiredError,
    PersistenceBackend,
    SubjectResolver,
    import_fastapi,
)
from safecode.enterprise.api.settings import TeamServerSettings

SERVICE_NAME = "safecode-enterprise-team-server"
API_VERSION = "2.1.0-planned"


@dataclass(frozen=True)
class AppState:
    settings: TeamServerSettings
    backend: PersistenceBackend
    subject_resolver: SubjectResolver


def create_app(
    *,
    settings: TeamServerSettings,
    backend: PersistenceBackend,
    subject_resolver: SubjectResolver,
) -> Any:
    FastAPI = import_fastapi()
    from fastapi.responses import JSONResponse

    app = FastAPI(title="SafeCodeAgent Enterprise Team Server", version=API_VERSION)
    app.state.enterprise = AppState(
        settings=settings,
        backend=backend,
        subject_resolver=subject_resolver,
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        if backend.probe():
            return JSONResponse({"status": "ok"})
        return JSONResponse(
            status_code=503,
            content={
                "type": "about:blank",
                "title": "Service Unavailable",
                "status": 503,
                "detail": "persistence backend unavailable",
            },
            media_type="application/problem+json",
        )

    @app.get("/version")
    def version() -> dict[str, str]:
        return {
            "service": SERVICE_NAME,
            "api_version": API_VERSION,
            "contract_status": CONTRACT_STATUS,
        }

    @app.exception_handler(AuthenticationRequiredError)
    def authentication_required(_request, exc: AuthenticationRequiredError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={
                "type": "about:blank",
                "title": "Unauthorized",
                "status": 401,
                "detail": str(exc),
            },
            media_type="application/problem+json",
        )

    return app
