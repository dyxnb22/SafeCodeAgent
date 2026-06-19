"""Signed GitHub webhook ingest route (v2.2.1-T2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse

from safecode.enterprise.api.app import AppState
from safecode.enterprise.api.routes._deps import get_app_state, get_backend
from safecode.enterprise.connectors.github_app import (
    GitHubAppConfigurationError,
    GitHubWebhookError,
    build_github_app_config,
    parse_webhook_event,
    verify_webhook_signature,
)
from safecode.enterprise.persistence.webhook_store import payload_digest
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.worker.commands import command_queue_for, start_run
from safecode.enterprise.persistence.webhook_store import WebhookDeliveryConflictError
from safecode.enterprise.worker.queue import IdempotencyConflictError

router = APIRouter(prefix="/v2/webhooks", tags=["webhooks"])

_SUPPORTED_EVENTS = frozenset({"pull_request"})
_SUPPORTED_ACTIONS = frozenset({"opened", "synchronize", "reopened", "ready_for_review"})


def _webhook_subject(tenant_id: str) -> RBACSubject:
    return RBACSubject(
        actor_id="github:webhook",
        tenant_id=tenant_id,
        roles=(Role.developer,),
    )


def _problem(status: int, detail: str) -> JSONResponse:
    titles = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        409: "Conflict",
        413: "Payload Too Large",
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


@router.post("/github")
async def github_webhook(
    request: Request,
    response: Response,
    state: Annotated[AppState, Depends(get_app_state)],
    backend: Annotated[object, Depends(get_backend)],
    x_github_delivery: Annotated[str | None, Header()] = None,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    x_github_event: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    try:
        app_config = build_github_app_config(
            app_id=state.settings.github_app_id,
            installation_id=state.settings.github_installation_id,
            private_key_pem=state.settings.github_private_key_pem,
            webhook_secret=state.settings.github_webhook_secret,
            webhook_tenant_id=state.settings.github_webhook_tenant_id,
            api_base_url=state.settings.github_api_base_url,
            project_root=state.project_root,
        )
    except GitHubAppConfigurationError as exc:
        return _problem(503, str(exc))

    if app_config is None or app_config.webhook_secret is None:
        return _problem(503, "github webhook secret is not configured")

    if not x_github_delivery:
        return _problem(400, "X-GitHub-Delivery header is required")
    if not x_github_event:
        return _problem(400, "X-GitHub-Event header is required")
    if x_github_event not in _SUPPORTED_EVENTS:
        return _problem(400, f"unsupported webhook event: {x_github_event}")

    body = await request.body()
    try:
        verify_webhook_signature(
            body=body,
            secret=app_config.webhook_secret,
            signature_header=x_hub_signature_256,
        )
    except GitHubWebhookError as exc:
        return _problem(401, str(exc))

    digest = payload_digest(body)
    webhook_store = getattr(backend, "webhooks", None)
    if webhook_store is not None:
        existing = webhook_store.get_delivery(delivery_id=x_github_delivery)
        if existing is not None:
            if existing.payload_digest != digest:
                return _problem(409, "delivery id already bound to a different payload")
            response.status_code = 202
            return {
                "run_id": existing.run_id,
                "status": "accepted",
                "delivery_id": existing.delivery_id,
                "replay": "true",
            }

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _problem(400, "invalid webhook json payload")

    if not isinstance(payload, dict):
        return _problem(400, "invalid webhook json payload")

    try:
        action, repo_full_name, pr_number, installation_id = parse_webhook_event(payload)
    except GitHubWebhookError as exc:
        return _problem(400, str(exc))

    if action not in _SUPPORTED_ACTIONS:
        return _problem(400, f"unsupported pull_request action: {action}")

    if installation_id != app_config.installation_id:
        return _problem(403, "installation id mismatch")

    tenant_id = app_config.webhook_tenant_id
    input_ref = json.dumps(
        {
            "source": "github_webhook",
            "repo": repo_full_name,
            "pr_number": pr_number,
            "action": action,
            "delivery_id": x_github_delivery,
        },
        sort_keys=True,
    )
    project_root = state.project_root
    if project_root is None:
        sac_root = getattr(backend, "sac_root", None)
        if sac_root is not None:
            project_root = sac_root.parent
        else:
            project_root = Path(".")
    queue = command_queue_for(backend)
    try:
        accepted = start_run(
            backend,
            queue,
            tenant_id=tenant_id,
            idempotency_key=x_github_delivery,
            task_type="pr_review",
            input_ref=input_ref,
            subject=_webhook_subject(tenant_id),
            project_root=project_root,
        )
    except (IdempotencyConflictError, WebhookDeliveryConflictError) as exc:
        return _problem(409, str(exc))
    except ValueError as exc:
        return _problem(400, str(exc))

    if webhook_store is not None:
        try:
            webhook_store.record_delivery(
                delivery_id=x_github_delivery,
                tenant_id=tenant_id,
                event_type=x_github_event,
                run_id=accepted.run_id,
                idempotency_key=x_github_delivery,
                payload_digest=digest,
            )
        except Exception as exc:
            if "already bound" in str(exc).lower():
                return _problem(409, str(exc))
            raise

    response.status_code = 202
    return {
        "run_id": accepted.run_id,
        "status": accepted.status,
        "delivery_id": x_github_delivery,
        "replay": "false",
    }
