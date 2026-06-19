"""Signed CI callback handler tests (v2.2.4-T2)."""

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
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.scanners.results import (
    CI_CALLBACK_SCHEMA_VERSION,
    load_ci_result_record,
    sign_ci_callback_body,
)
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint
from safecode.enterprise.workflow.orchestrator import build_initial_state, utc_now_iso
from safecode.enterprise.workflow.types import TaskType

CALLBACK_SECRET = "test-ci-callback-secret"
DELIVERY_ID = "ci-delivery-00123456"
TENANT_ID = "tenant-ci"
COMMIT_SHA = "b" * 40


def _generate_private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def _settings() -> TeamServerSettings:
    return TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.LOCAL,
            "operator_actor": "user:dev",
            "github_webhook_secret": CALLBACK_SECRET,
            "github_app_id": "123456",
            "github_installation_id": "987654",
            "github_private_key_pem": _generate_private_key_pem(),
        }
    )


def _seed_run(backend: LocalBackend, tmp_path: Path, *, commit_sha: str = COMMIT_SHA) -> str:
    run_id = "run-ci000000000001"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:dev",
        repo_root=tmp_path,
        run_id=run_id,
        tenant_id=TENANT_ID,
    )
    state = state.model_copy(
        update={
            "repo": state.repo.model_copy(update={"commit_sha": commit_sha}),
            "updated_at": utc_now_iso(),
        }
    )
    backend.runs.save_checkpoint(
        tenant_id=TENANT_ID,
        checkpoint=RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=run_id,
            completed_nodes=[],
            next_node="classify_request",
            state=state,
        ),
    )
    return run_id


def _client(tmp_path: Path) -> tuple[TestClient, LocalBackend, str]:
    backend = LocalBackend(tmp_path / ".sac")
    run_id = _seed_run(backend, tmp_path)
    app = create_app(
        settings=_settings(),
        backend=backend,
        subject_resolver=lambda: RBACSubject(
            actor_id="user:dev",
            tenant_id=TENANT_ID,
            roles=(Role.developer,),
        ),
        project_root=tmp_path,
    )
    return TestClient(app), backend, run_id


def _payload(*, run_id: str, outcome: str = "passed") -> dict[str, object]:
    return {
        "schema_version": CI_CALLBACK_SCHEMA_VERSION,
        "delivery_id": DELIVERY_ID,
        "run_id": run_id,
        "outcome": outcome,
        "commit_sha": COMMIT_SHA,
        "scanner": "semgrep",
        "tool_version": "1.90.0",
    }


def _signed_request(
    client: TestClient,
    *,
    payload: dict[str, object],
    delivery_id: str = DELIVERY_ID,
    tenant_id: str = TENANT_ID,
    secret: str = CALLBACK_SECRET,
    signature: str | None = None,
) -> object:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "X-Tenant-Id": tenant_id,
        "Idempotency-Key": delivery_id,
        "Content-Type": "application/json",
    }
    if signature is None:
        headers["X-CI-Signature-256"] = sign_ci_callback_body(body, secret=secret)
    elif signature:
        headers["X-CI-Signature-256"] = signature
    return client.post("/v2/ci/callback", content=body, headers=headers)


def test_valid_signed_callback_updates_one_run(tmp_path: Path) -> None:
    client, backend, run_id = _client(tmp_path)
    response = _signed_request(client, payload=_payload(run_id=run_id))
    assert response.status_code == 202
    body = response.json()
    assert body["replay"] == "false"
    assert body["run_id"] == run_id

    checkpoint = backend.runs.load_checkpoint(tenant_id=TENANT_ID, run_id=run_id)
    assert checkpoint.state.validation is not None
    assert checkpoint.state.validation.passed is True
    assert checkpoint.state.validation.details["source"] == "ci_callback"

    record = load_ci_result_record(backend.sac_root, run_id=run_id, delivery_id=DELIVERY_ID)
    assert record is not None
    assert record.outcome == "passed"

    events = backend.trace.list_events(tenant_id=TENANT_ID, run_id=run_id)
    assert any(event.type is TraceEventType.validation_result for event in events)


def test_replay_delivery_id_returns_same_result_without_second_write(tmp_path: Path) -> None:
    client, backend, run_id = _client(tmp_path)
    first = _signed_request(client, payload=_payload(run_id=run_id))
    second = _signed_request(client, payload=_payload(run_id=run_id))
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]
    assert second.json()["replay"] == "true"


def test_bad_signature_fails_closed(tmp_path: Path) -> None:
    client, _backend, run_id = _client(tmp_path)
    response = _signed_request(
        client,
        payload=_payload(run_id=run_id),
        signature="sha256=deadbeef",
    )
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


def test_schema_mismatch_rejected(tmp_path: Path) -> None:
    client, _backend, run_id = _client(tmp_path)
    payload = _payload(run_id=run_id)
    payload["schema_version"] = "9.9"
    response = _signed_request(client, payload=payload)
    assert response.status_code == 400


def test_unknown_outcome_rejected(tmp_path: Path) -> None:
    client, _backend, run_id = _client(tmp_path)
    payload = _payload(run_id=run_id)
    payload["outcome"] = "maybe"
    response = _signed_request(client, payload=payload)
    assert response.status_code == 400


def test_commit_mismatch_fails_closed(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    run_id = _seed_run(backend, tmp_path, commit_sha="c" * 40)
    app = create_app(
        settings=_settings(),
        backend=backend,
        subject_resolver=lambda: RBACSubject(
            actor_id="user:dev",
            tenant_id=TENANT_ID,
            roles=(Role.developer,),
        ),
        project_root=tmp_path,
    )
    client = TestClient(app)
    response = _signed_request(client, payload=_payload(run_id=run_id))
    assert response.status_code == 403


def test_delivery_id_conflict_fails_closed(tmp_path: Path) -> None:
    client, backend, run_id = _client(tmp_path)
    backend.webhooks.record_delivery(
        delivery_id=DELIVERY_ID,
        tenant_id=TENANT_ID,
        event_type="ci_callback",
        run_id="run-other000000001",
        idempotency_key=DELIVERY_ID,
        payload_digest="abc123",
    )
    response = _signed_request(client, payload=_payload(run_id=run_id))
    assert response.status_code == 409


def test_missing_secret_configuration_fails_closed(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    run_id = _seed_run(backend, tmp_path)
    settings = TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.LOCAL,
            "operator_actor": "user:dev",
        }
    )
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=lambda: RBACSubject(
            actor_id="user:dev",
            tenant_id=TENANT_ID,
            roles=(Role.developer,),
        ),
        project_root=tmp_path,
    )
    client = TestClient(app)
    response = _signed_request(client, payload=_payload(run_id=run_id))
    assert response.status_code == 503
