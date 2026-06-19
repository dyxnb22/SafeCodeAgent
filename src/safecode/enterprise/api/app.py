"""FastAPI application factory for the Team Server (v2.1.4-T1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from safecode.enterprise.api.contracts import CONTRACT_STATUS
from safecode.enterprise.api.dependencies import (
    AuthenticationRequiredError,
    PersistenceBackend,
    SubjectResolver,
    import_fastapi,
)
from safecode.enterprise.api.exceptions import (
    ApprovalForbiddenError,
    ApprovalRequestNotFoundError,
    IdempotencyKeyRequiredError,
    TenantScopeDeniedError,
)
from safecode.enterprise.api.rate_limit import InflightLimitExceeded, RateLimitExceeded, TenantRateLimiter
from safecode.enterprise.api.settings import TeamServerSettings, parse_cors_allowed_origins
from safecode.enterprise.auth.oidc import OidcValidator
from safecode.enterprise.persistence.exceptions import TenantBoundaryError
from safecode.enterprise.worker.queue import IdempotencyConflictError
from safecode.enterprise.workflow.exceptions import CheckpointCorruptedError

SERVICE_NAME = "safecode-enterprise-team-server"
API_VERSION = "2.1.0-planned"


@dataclass(frozen=True)
class AppState:
    settings: TeamServerSettings
    backend: PersistenceBackend
    subject_resolver: SubjectResolver
    rate_limiter: TenantRateLimiter
    oidc_validator: OidcValidator | None = None
    eval_baselines_root: Path | None = None
    project_root: Path | None = None


def create_app(
    *,
    settings: TeamServerSettings,
    backend: PersistenceBackend,
    subject_resolver: SubjectResolver,
    oidc_validator: OidcValidator | None = None,
    eval_baselines_root: Path | None = None,
    project_root: Path | None = None,
) -> Any:
    FastAPI = import_fastapi()
    from fastapi.responses import JSONResponse

    from safecode.enterprise.api.routes import (
        approvals_router,
        ci_callback_router,
        eval_router,
        evidence_router,
        runs_router,
        traces_router,
        webhooks_router,
    )

    app = FastAPI(title="SafeCodeAgent Enterprise Team Server", version=API_VERSION)
    rate_limiter = TenantRateLimiter.from_settings(settings)
    app.state.enterprise = AppState(
        settings=settings,
        backend=backend,
        subject_resolver=subject_resolver,
        rate_limiter=rate_limiter,
        oidc_validator=oidc_validator,
        eval_baselines_root=eval_baselines_root,
        project_root=project_root,
    )
    app.include_router(runs_router)
    app.include_router(traces_router)
    app.include_router(approvals_router)
    app.include_router(evidence_router)
    app.include_router(eval_router)
    app.include_router(webhooks_router)
    app.include_router(ci_callback_router)

    cors_origins = parse_cors_allowed_origins(settings.cors_allowed_origins)
    if cors_origins:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Tenant-Id", "Idempotency-Key"],
        )

    @app.middleware("http")
    async def enforce_v2_rate_limits(request, call_next):
        if request.url.path.startswith("/v2"):
            tenant = (
                request.headers.get("X-Tenant-Id")
                or request.query_params.get("tenant_id")
                or "local"
            )
            try:
                rate_limiter.check_request(tenant)
            except RateLimitExceeded as exc:
                return JSONResponse(
                    status_code=429,
                    content={
                        "type": "about:blank",
                        "title": "Too Many Requests",
                        "status": 429,
                        "detail": exc.detail,
                    },
                    media_type="application/problem+json",
                )
        return await call_next(request)

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

    @app.exception_handler(TenantScopeDeniedError)
    def tenant_scope_denied(_request, exc: TenantScopeDeniedError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "type": "about:blank",
                "title": "Forbidden",
                "status": 403,
                "detail": str(exc),
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(TenantBoundaryError)
    def tenant_boundary_violation(_request, exc: TenantBoundaryError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "type": "about:blank",
                "title": "Forbidden",
                "status": 403,
                "detail": str(exc),
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(ApprovalForbiddenError)
    def approval_forbidden(_request, exc: ApprovalForbiddenError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "type": "about:blank",
                "title": "Forbidden",
                "status": 403,
                "detail": str(exc),
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(ApprovalRequestNotFoundError)
    def approval_not_found(_request, exc: ApprovalRequestNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "type": "about:blank",
                "title": "Not Found",
                "status": 404,
                "detail": str(exc),
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(IdempotencyKeyRequiredError)
    def idempotency_required(_request, exc: IdempotencyKeyRequiredError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "type": "about:blank",
                "title": "Bad Request",
                "status": 400,
                "detail": str(exc),
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(IdempotencyConflictError)
    def idempotency_conflict(_request, exc: IdempotencyConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "type": "about:blank",
                "title": "Conflict",
                "status": 409,
                "detail": str(exc),
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(ValueError)
    def invalid_command(_request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "type": "about:blank",
                "title": "Bad Request",
                "status": 400,
                "detail": str(exc),
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(RateLimitExceeded)
    def rate_limit_exceeded(_request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "type": "about:blank",
                "title": "Too Many Requests",
                "status": 429,
                "detail": exc.detail,
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(InflightLimitExceeded)
    def inflight_limit_exceeded(_request, exc: InflightLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "type": "about:blank",
                "title": "Too Many Requests",
                "status": 429,
                "detail": exc.detail,
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(CheckpointCorruptedError)
    def checkpoint_missing(_request, exc: CheckpointCorruptedError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "type": "about:blank",
                "title": "Not Found",
                "status": 404,
                "detail": str(exc),
            },
            media_type="application/problem+json",
        )

    return app
