"""Signed CI callback ingest route (v2.2.4-T2)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import SecretStr

from safecode.enterprise.api.app import AppState
from safecode.enterprise.api.routes._deps import (
    get_app_state,
    get_backend,
    require_idempotency_key,
    require_tenant_header,
)
from safecode.enterprise.persistence.webhook_store import WebhookDeliveryConflictError
from safecode.enterprise.scanners.results import (
    CiCallbackSchemaError,
    CiCallbackSignatureError,
    apply_ci_callback_to_run,
    digest_ci_callback_body,
    parse_ci_callback_request,
    verify_ci_callback_signature,
)

router = APIRouter(prefix="/v2/ci", tags=["ci"])
_logger = logging.getLogger(__name__)


def _problem(status: int, detail: str) -> JSONResponse:
    titles = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        409: "Conflict",
        503: "Service Unavailable",
    }
    return JSONResponse(
        status_code=status,
        content={
            "type": "about:blank",
            "title": titles.get(status, "Error"),
            "status": status,
            "detail": detail,
        },
        media_type="application/problem+json",
    )


def _callback_secret(state: AppState) -> SecretStr | None:
    return state.settings.ci_callback_secret


@router.post("/callback")
async def ci_callback(
    request: Request,
    response: Response,
    state: Annotated[AppState, Depends(get_app_state)],
    backend: Annotated[object, Depends(get_backend)],
    tenant_id: Annotated[str, Depends(require_tenant_header)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
    x_ci_signature_256: Annotated[str | None, Header(alias="X-CI-Signature-256")] = None,
) -> dict[str, str]:
    secret = _callback_secret(state)
    if secret is None:
        _logger.warning("ci callback rejected: ci_callback_secret is not configured")
        return _problem(503, "ci callback secret is not configured")

    body = await request.body()
    try:
        verify_ci_callback_signature(
            body=body,
            secret=secret.get_secret_value(),
            signature_header=x_ci_signature_256,
        )
    except CiCallbackSignatureError as exc:
        return _problem(401, str(exc))

    digest = digest_ci_callback_body(body)
    webhook_store = getattr(backend, "webhooks", None)
    if webhook_store is not None:
        existing = webhook_store.get_delivery(delivery_id=idempotency_key)
        if existing is not None:
            if existing.payload_digest != digest:
                return _problem(409, "delivery id already bound to a different payload")
            response.status_code = 202
            return {
                "delivery_id": existing.delivery_id,
                "run_id": existing.run_id,
                "status": "accepted",
                "replay": "true",
            }

    try:
        callback = parse_ci_callback_request(body)
    except CiCallbackSchemaError as exc:
        return _problem(400, str(exc))

    if callback.delivery_id != idempotency_key:
        return _problem(400, "delivery_id must match Idempotency-Key header")

    try:
        record = apply_ci_callback_to_run(
            backend,
            tenant_id=tenant_id,
            request=callback,
            payload_digest_value=digest,
        )
    except ValueError as exc:
        message = str(exc)
        if "already bound" in message.lower():
            return _problem(409, message)
        if "tenant" in message.lower() or "commit" in message.lower():
            return _problem(403, message)
        return _problem(400, message)
    except WebhookDeliveryConflictError as exc:
        return _problem(409, str(exc))

    if webhook_store is not None:
        try:
            webhook_store.record_delivery(
                delivery_id=idempotency_key,
                tenant_id=tenant_id,
                event_type="ci_callback",
                run_id=record.run_id,
                idempotency_key=idempotency_key,
                payload_digest=digest,
            )
        except Exception as exc:
            if "already bound" in str(exc).lower():
                return _problem(409, str(exc))
            raise

    response.status_code = 202
    return {
        "delivery_id": record.delivery_id,
        "run_id": record.run_id,
        "status": "accepted",
        "replay": "false",
    }
