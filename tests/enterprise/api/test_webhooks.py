"""Signed GitHub webhook handler tests (v2.2.1-T2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.connectors.github_app import MAX_WEBHOOK_BODY_BYTES, sign_webhook_body
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role

APP_ID = "123456"
INSTALLATION_ID = "987654"
WEBHOOK_SECRET = "test-webhook-secret-value"
DELIVERY_ID = "delivery-id-00123456"


def _generate_private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def _pull_request_payload(*, installation_id: str = INSTALLATION_ID) -> dict[str, object]:
    return {
        "action": "opened",
        "installation": {"id": int(installation_id)},
        "repository": {"full_name": "acme/sample-app"},
        "pull_request": {"number": 42},
    }


def _settings(tmp_path: Path) -> TeamServerSettings:
    return TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.LOCAL,
            "operator_actor": "user:dev",
            "github_app_id": APP_ID,
            "github_installation_id": INSTALLATION_ID,
            "github_private_key_pem": _generate_private_key_pem(),
            "github_webhook_secret": WEBHOOK_SECRET,
            "github_webhook_tenant_id": "tenant-github",
        }
    )


def _client(tmp_path: Path) -> tuple[TestClient, LocalBackend]:
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=_settings(tmp_path),
        backend=backend,
        subject_resolver=lambda: RBACSubject(
            actor_id="user:dev",
            tenant_id="tenant-github",
            roles=(Role.developer,),
        ),
        project_root=tmp_path,
    )
    return TestClient(app), backend


def _signed_request(
    client: TestClient,
    *,
    payload: dict[str, object],
    delivery_id: str = DELIVERY_ID,
    secret: str = WEBHOOK_SECRET,
    event: str = "pull_request",
    signature: str | None = None,
) -> object:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "X-GitHub-Delivery": delivery_id,
        "X-GitHub-Event": event,
        "Content-Type": "application/json",
    }
    if signature is None:
        headers["X-Hub-Signature-256"] = sign_webhook_body(body, secret=secret)
    elif signature:
        headers["X-Hub-Signature-256"] = signature
    return client.post("/v2/webhooks/github", content=body, headers=headers)


def test_valid_signed_delivery_queues_one_command(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    response = _signed_request(client, payload=_pull_request_payload())
    assert response.status_code == 202
    body = response.json()
    assert body["replay"] == "false"
    run_id = body["run_id"]
    assert run_id

    command = backend.commands.get_command(
        tenant_id="tenant-github",
        idempotency_key=DELIVERY_ID,
    )
    assert command is not None
    assert command.run_id == run_id
    assert command.command == "start"

    delivery = backend.webhooks.get_delivery(delivery_id=DELIVERY_ID)
    assert delivery is not None
    assert delivery.run_id == run_id


def test_replay_delivery_id_returns_same_run_without_second_command(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    first = _signed_request(client, payload=_pull_request_payload())
    second = _signed_request(client, payload=_pull_request_payload())
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]
    assert second.json()["replay"] == "true"

    command = backend.commands.get_command(tenant_id="tenant-github", idempotency_key=DELIVERY_ID)
    assert command is not None
    assert command.command == "start"


def test_bad_signature_fails_closed(tmp_path: Path) -> None:
    client, _backend = _client(tmp_path)
    response = _signed_request(
        client,
        payload=_pull_request_payload(),
        signature="sha256=deadbeef",
    )
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


def test_missing_secret_configuration_fails_closed(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    settings = TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.LOCAL,
            "operator_actor": "user:dev",
        }
    )
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=lambda: RBACSubject(actor_id="user:dev"),
        project_root=tmp_path,
    )
    client = TestClient(app)
    response = _signed_request(client, payload=_pull_request_payload(), secret=WEBHOOK_SECRET)
    assert response.status_code == 503


def test_oversized_body_fails_closed(tmp_path: Path) -> None:
    client, _backend = _client(tmp_path)
    payload = _pull_request_payload()
    payload["padding"] = "x" * (MAX_WEBHOOK_BODY_BYTES + 1)
    response = _signed_request(client, payload=payload)
    assert response.status_code == 401


def test_unsupported_event_fails_closed(tmp_path: Path) -> None:
    client, _backend = _client(tmp_path)
    body = json.dumps(_pull_request_payload()).encode("utf-8")
    response = client.post(
        "/v2/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Delivery": DELIVERY_ID,
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sign_webhook_body(body, secret=WEBHOOK_SECRET),
        },
    )
    assert response.status_code == 400


def test_installation_mismatch_fails_closed(tmp_path: Path) -> None:
    client, _backend = _client(tmp_path)
    response = _signed_request(
        client,
        payload=_pull_request_payload(installation_id="111111"),
    )
    assert response.status_code == 403


def test_delivery_id_conflict_fails_closed(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    first = _signed_request(client, payload=_pull_request_payload())
    assert first.status_code == 202
    backend.webhooks.record_delivery(
        delivery_id="delivery-conflict01",
        tenant_id="tenant-github",
        event_type="pull_request",
        run_id="run-conflict000001",
        idempotency_key="delivery-conflict01",
        payload_digest="abc123",
    )
    body = json.dumps(_pull_request_payload()).encode("utf-8")
    response = client.post(
        "/v2/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Delivery": "delivery-conflict01",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": sign_webhook_body(body, secret=WEBHOOK_SECRET),
        },
    )
    assert response.status_code == 409
