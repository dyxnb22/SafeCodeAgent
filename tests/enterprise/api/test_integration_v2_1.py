"""Offline v2.1 Team Server integration suite (v2.1.7-T3)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oidc_fixtures import AUDIENCE, ISSUER, generate_oidc_test_keys

from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.dependencies import fail_closed_subject_resolver
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.auth.oidc import build_oidc_validator
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.persistence.strict_fake import StrictFakeBackend
from safecode.enterprise.rbac.models import Role
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.trace.session import project_root_for_sac
from safecode.enterprise.worker.runner import WorkerRunner
from safecode.enterprise.workflow.types import WorkflowStatus

_PR_FIXTURE = Path(__file__).resolve().parents[3] / "examples" / "enterprise" / "fixtures" / "pr_sql_injection"


def _server_settings() -> TeamServerSettings:
    return TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.SERVER,
            "database_url": "postgresql://user:pass@127.0.0.1:5432/enterprise",
            "oidc_issuer": ISSUER,
            "oidc_audience": AUDIENCE,
        }
    )


def _auth_headers(token: str, *, tenant_id: str = "tenant-a", idempotency_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": tenant_id,
        "Idempotency-Key": idempotency_key,
    }


def _server_client(
    tmp_path: Path,
    *,
    backend: LocalBackend | StrictFakeBackend | None = None,
    tenant_id: str = "tenant-a",
) -> tuple[TestClient, LocalBackend | StrictFakeBackend, str]:
    keys = generate_oidc_test_keys()
    settings = _server_settings()
    backend = backend or LocalBackend(tmp_path / ".sac")
    validator = build_oidc_validator(issuer=ISSUER, audience=AUDIENCE, jwks=keys.jwks)
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=fail_closed_subject_resolver(settings),
        oidc_validator=validator,
        project_root=tmp_path,
    )
    token = keys.sign(tenant_id=tenant_id, roles=["developer"])
    return TestClient(app), backend, token


def test_authenticated_start_run_worker_and_read(tmp_path: Path) -> None:
    client, backend, token = _server_client(tmp_path)
    fixture = _PR_FIXTURE / "pr.json"
    started = client.post(
        "/v2/runs",
        headers=_auth_headers(token, idempotency_key="integration-start01"),
        json={"task_type": "pr_review", "input_ref": str(fixture)},
    )
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    worker = WorkerRunner(backend, worker_id="integration-worker", project_root=tmp_path)
    for _ in range(30):
        worker.process_once()
        status = backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=run_id).state.status
        if status not in {WorkflowStatus.pending, WorkflowStatus.running}:
            break
    detail = client.get("/v2/runs/" + run_id, params={"tenant_id": "tenant-a"}, headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    assert detail.json()["run_id"] == run_id


def test_invalid_token_fails_closed(tmp_path: Path) -> None:
    client, _backend, _token = _server_client(tmp_path)
    response = client.get(
        "/v2/runs",
        params={"tenant_id": "tenant-a"},
        headers={"Authorization": "Bearer invalid.token.value"},
    )
    assert response.status_code == 401


def test_cross_tenant_read_fails_closed(tmp_path: Path) -> None:
    client, backend, token = _server_client(tmp_path)
    fixture = _PR_FIXTURE / "pr.json"
    started = client.post(
        "/v2/runs",
        headers=_auth_headers(token, idempotency_key="integration-start02"),
        json={"task_type": "pr_review", "input_ref": str(fixture)},
    )
    run_id = started.json()["run_id"]
    backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=run_id)
    response = client.get(
        f"/v2/runs/{run_id}",
        params={"tenant_id": "tenant-b"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_duplicate_command_idempotency_returns_same_run(tmp_path: Path) -> None:
    client, _backend, token = _server_client(tmp_path)
    fixture = _PR_FIXTURE / "pr.json"
    body = {"task_type": "pr_review", "input_ref": str(fixture)}
    headers = _auth_headers(token, idempotency_key="integration-idem0001")
    first = client.post("/v2/runs", headers=headers, json=body)
    second = client.post("/v2/runs", headers=headers, json=body)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]


def test_evidence_and_audit_verification(tmp_path: Path) -> None:
    client, backend, token = _server_client(tmp_path)
    fixture = _PR_FIXTURE / "pr.json"
    started = client.post(
        "/v2/runs",
        headers=_auth_headers(token, idempotency_key="integration-start03"),
        json={"task_type": "pr_review", "input_ref": str(fixture)},
    )
    run_id = started.json()["run_id"]
    backend.trace.emit_event(
        tenant_id="tenant-a",
        run_id=run_id,
        event_type=TraceEventType.node_start,
        node_id="classify_request",
        seq=1,
    )
    evidence = client.get(
        f"/v2/evidence/{run_id}",
        params={"tenant_id": "tenant-a"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert evidence.status_code == 200
    assert evidence.content.startswith(b"PK")
    chain = EnterpriseAuditChain(project_root_for_sac(backend.sac_root))
    ok, _reason = chain.verify_integrity()
    assert ok


def test_strict_fake_lane_supports_authenticated_reads(tmp_path: Path) -> None:
    backend = StrictFakeBackend(tmp_path / ".sac")
    client, backend, token = _server_client(tmp_path, backend=backend)
    response = client.get(
        "/v2/runs",
        params={"tenant_id": "tenant-a"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.postgres_integration
def test_postgres_lane_authenticated_run_persists(postgres_backend, tmp_path: Path) -> None:
    keys = generate_oidc_test_keys()
    settings = _server_settings()
    validator = build_oidc_validator(issuer=ISSUER, audience=AUDIENCE, jwks=keys.jwks)
    app = create_app(
        settings=settings,
        backend=postgres_backend,
        subject_resolver=fail_closed_subject_resolver(settings),
        oidc_validator=validator,
        project_root=tmp_path,
    )
    client = TestClient(app)
    token = keys.sign(tenant_id="tenant-a", roles=[Role.developer.value])
    fixture = _PR_FIXTURE / "pr.json"
    started = client.post(
        "/v2/runs",
        headers=_auth_headers(token, idempotency_key="integration-pg-start1"),
        json={"task_type": "pr_review", "input_ref": str(fixture)},
    )
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    checkpoint = postgres_backend.runs.load_checkpoint(tenant_id="tenant-a", run_id=run_id)
    assert checkpoint.state.tenant_id == "tenant-a"
