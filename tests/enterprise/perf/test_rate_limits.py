"""API rate limit tests (v2.5.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.rate_limit import RateLimitExceeded, TenantRateLimiter
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role


def _subject_resolver(tenant_id: str = "tenant-a") -> callable:
    def _resolve() -> RBACSubject:
        return RBACSubject(actor_id="user:dev", tenant_id=tenant_id, roles=(Role.developer,))

    return _resolve


def _client(tmp_path: Path, *, rpm: int = 3, max_inflight: int = 2) -> TestClient:
    settings = TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.LOCAL,
            "operator_actor": "user:dev",
            "rate_limit_rpm": rpm,
            "max_inflight_runs": max_inflight,
        }
    )
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=_subject_resolver(),
        project_root=tmp_path,
    )
    return TestClient(app)


def test_rate_limiter_blocks_after_rpm_budget(tmp_path: Path) -> None:
    client = _client(tmp_path, rpm=2)
    for _ in range(2):
        assert (
            client.get(
                "/v2/runs",
                params={"tenant_id": "tenant-a"},
                headers={"X-Tenant-Id": "tenant-a"},
            ).status_code
            == 200
        )
    blocked = client.get(
        "/v2/runs",
        params={"tenant_id": "tenant-a"},
        headers={"X-Tenant-Id": "tenant-a"},
    )
    assert blocked.status_code == 429
    assert blocked.headers["content-type"].startswith("application/problem+json")


def test_healthz_is_not_rate_limited(tmp_path: Path) -> None:
    client = _client(tmp_path, rpm=1)
    assert client.get("/healthz").status_code == 200
    assert client.get("/healthz").status_code == 200


def test_inflight_limit_blocks_new_run(tmp_path: Path) -> None:
    client = _client(tmp_path, max_inflight=1)
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    body = {"task_type": "pr_review", "input_ref": str(fixture)}
    first = client.post(
        "/v2/runs",
        headers={"X-Tenant-Id": "tenant-a", "Idempotency-Key": "idem-rate-001"},
        json=body,
    )
    assert first.status_code == 202
    second = client.post(
        "/v2/runs",
        headers={"X-Tenant-Id": "tenant-a", "Idempotency-Key": "idem-rate-002"},
        json=body,
    )
    assert second.status_code == 429


def test_token_bucket_is_tenant_scoped() -> None:
    limiter = TenantRateLimiter(rate_limit_rpm=1, max_inflight_runs=5)
    limiter.check_request("tenant-a")
    limiter.check_request("tenant-b")
    with pytest.raises(RateLimitExceeded):
        limiter.check_request("tenant-a")
