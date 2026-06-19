"""Read endpoint tests for the Team Server API (v2.1.4-T2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "persistence"))
from backend_contract import (  # noqa: E402
    sample_checkpoint,
    sample_request,
)

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.dependencies import fail_closed_subject_resolver
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.auth.oidc import build_oidc_validator
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.trace.events import TraceEventType

from oidc_fixtures import AUDIENCE, ISSUER, generate_oidc_test_keys

_BASELINES_ROOT = ROOT / "tests" / "enterprise" / "eval" / "baselines"
_SECRET = "ghp_" + ("z" * 36)


def _settings(**overrides) -> TeamServerSettings:
    return TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.LOCAL,
            "operator_actor": "user:test",
            **overrides,
        }
    )


def _subject_resolver(*, tenant_id: str = "tenant-a", actor_id: str = "user:viewer") -> callable:
    def _resolve() -> RBACSubject:
        return RBACSubject(
            actor_id=actor_id,
            tenant_id=tenant_id,
            roles=(Role.viewer,),
        )

    return _resolve


def _client(
    tmp_path: Path,
    *,
    tenant_id: str = "tenant-a",
    baselines_root: Path | None = _BASELINES_ROOT,
) -> tuple[TestClient, LocalBackend]:
    settings = _settings()
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=_subject_resolver(tenant_id=tenant_id),
        eval_baselines_root=baselines_root,
    )
    return TestClient(app), backend


def _seed_run(
    backend: LocalBackend,
    *,
    run_id: str = "run-api-read001",
    tenant_id: str = "tenant-a",
) -> None:
    checkpoint = sample_checkpoint(run_id=run_id, tenant_id=tenant_id)
    backend.runs.save_checkpoint(tenant_id=tenant_id, checkpoint=checkpoint)


def test_list_and_get_runs_are_tenant_scoped(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    _seed_run(backend, run_id="run-api-read001", tenant_id="tenant-a")
    _seed_run(backend, run_id="run-api-read002", tenant_id="tenant-b")

    response = client.get("/v2/runs", params={"tenant_id": "tenant-a"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["run_id"] == "run-api-read001"
    assert payload["items"][0]["tenant_id"] == "tenant-a"

    detail = client.get("/v2/runs/run-api-read001", params={"tenant_id": "tenant-a"})
    assert detail.status_code == 200
    body = detail.json()
    assert body["run_id"] == "run-api-read001"
    assert body["status_url"].endswith("tenant_id=tenant-a")


def test_cross_tenant_query_is_forbidden(tmp_path: Path) -> None:
    client, backend = _client(tmp_path, tenant_id="tenant-a")
    _seed_run(backend)

    response = client.get("/v2/runs", params={"tenant_id": "tenant-b"})
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")


def test_missing_subject_returns_401(tmp_path: Path) -> None:
    settings = TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.SERVER,
            "database_url": "postgresql://user:pass@127.0.0.1:5432/enterprise",
            "oidc_issuer": ISSUER,
            "oidc_audience": AUDIENCE,
        }
    )
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=fail_closed_subject_resolver(settings),
    )
    client = TestClient(app)
    response = client.get("/v2/runs", params={"tenant_id": "tenant-a"})
    assert response.status_code == 401


def _server_client(
    tmp_path: Path,
    *,
    keys=None,
    token: str | None = None,
) -> tuple[TestClient, LocalBackend, str | None]:
    keys = keys or generate_oidc_test_keys()
    settings = TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.SERVER,
            "database_url": "postgresql://user:pass@127.0.0.1:5432/enterprise",
            "oidc_issuer": ISSUER,
            "oidc_audience": AUDIENCE,
        }
    )
    validator = build_oidc_validator(issuer=ISSUER, audience=AUDIENCE, jwks=keys.jwks)
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=fail_closed_subject_resolver(settings),
        oidc_validator=validator,
        eval_baselines_root=_BASELINES_ROOT,
    )
    bearer = token or keys.sign(tenant_id="tenant-a", roles=["viewer"])
    return TestClient(app), backend, bearer


def test_server_mode_bearer_token_resolves_subject(tmp_path: Path) -> None:
    client, backend, token = _server_client(tmp_path)
    _seed_run(backend, run_id="run-api-read001", tenant_id="tenant-a")

    response = client.get(
        "/v2/runs",
        params={"tenant_id": "tenant-a"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_server_mode_missing_tenant_claim_returns_401(tmp_path: Path) -> None:
    keys = generate_oidc_test_keys()
    token = keys.sign(tenant_id=None)
    client, _backend, _token = _server_client(tmp_path, keys=keys, token=token)

    response = client.get(
        "/v2/runs",
        params={"tenant_id": "tenant-a"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_server_mode_cross_tenant_query_is_forbidden(tmp_path: Path) -> None:
    client, backend, token = _server_client(tmp_path)
    _seed_run(backend, run_id="run-api-read001", tenant_id="tenant-a")

    response = client.get(
        "/v2/runs",
        params={"tenant_id": "tenant-b"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_list_approvals_filters_by_status(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    run_id = "run-api-read001"
    _seed_run(backend, run_id=run_id)
    pending = sample_request(run_id=run_id, request_id="approval-pending01", tenant_id="tenant-a")
    backend.approvals.save_request(tenant_id="tenant-a", request=pending)
    approved = sample_request(run_id=run_id, request_id="approval-approved01", tenant_id="tenant-a")
    saved = backend.approvals.save_request(tenant_id="tenant-a", request=approved)
    backend.approvals.decide_request(
        tenant_id="tenant-a",
        run_id=run_id,
        request_id=saved.request_id,
        decision="approved",
        decision_actor="user:reviewer",
    )

    response = client.get("/v2/approvals", params={"tenant_id": "tenant-a", "status": "pending"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["approval_id"] == "approval-pending01"
    assert items[0]["status"] == "pending"


def test_timeline_and_trace_endpoints_return_redacted_shapes(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    run_id = "run-api-read001"
    _seed_run(backend, run_id=run_id)
    backend.trace.emit_event(
        tenant_id="tenant-a",
        run_id=run_id,
        event_type=TraceEventType.model_call_start,
        node_id="analyze",
        seq=1,
        payload={"raw_prompt": _SECRET, "debug_payload": "internal"},
    )

    timeline = client.get(f"/v2/runs/{run_id}/timeline", params={"tenant_id": "tenant-a"})
    assert timeline.status_code == 200
    timeline_body = timeline.json()
    assert timeline_body["run_id"] == run_id
    assert "events" in timeline_body

    trace = client.get(f"/v2/runs/{run_id}/trace", params={"tenant_id": "tenant-a"})
    assert trace.status_code == 200
    trace_body = trace.json()
    assert trace_body["redaction_profile"] == "strict"
    assert trace_body["events"]
    serialized = json.dumps(trace_body)
    assert _SECRET not in serialized
    assert "raw_prompt" not in serialized
    assert "debug" not in serialized
    for event in trace_body["events"]:
        assert set(event.keys()) == {"event_type", "timestamp"}


def test_evidence_export_returns_zip(tmp_path: Path) -> None:
    client, backend = _client(tmp_path)
    run_id = "run-api-read001"
    _seed_run(backend, run_id=run_id)
    backend.trace.emit_event(
        tenant_id="tenant-a",
        run_id=run_id,
        event_type=TraceEventType.node_start,
        node_id="classify_request",
        seq=1,
    )

    response = client.get(f"/v2/evidence/{run_id}", params={"tenant_id": "tenant-a"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert response.content.startswith(b"PK")


def test_eval_baselines_lists_checked_in_suites(tmp_path: Path) -> None:
    client, _backend = _client(tmp_path)
    response = client.get("/v2/eval/baselines", params={"tenant_id": "tenant-a"})
    assert response.status_code == 200
    suites = {item["suite"] for item in response.json()["items"]}
    assert "retrieval" in suites
    assert "pr_review" in suites


def test_missing_run_returns_404(tmp_path: Path) -> None:
    client, _backend = _client(tmp_path)
    response = client.get("/v2/runs/run-missing01", params={"tenant_id": "tenant-a"})
    assert response.status_code == 404
