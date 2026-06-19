"""FastAPI probe endpoint tests (v2.1.4-T1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.dependencies import fail_closed_subject_resolver
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.persistence.local_backend import LocalBackend


@dataclass
class BrokenBackend:
    def probe(self) -> bool:
        return False


def _settings(**overrides) -> TeamServerSettings:
    return TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.LOCAL,
            "operator_actor": "user:test",
            **overrides,
        }
    )


def test_healthz_returns_ok(tmp_path: Path) -> None:
    settings = _settings()
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=fail_closed_subject_resolver(settings),
    )
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_ok_when_backend_probes(tmp_path: Path) -> None:
    settings = _settings()
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=fail_closed_subject_resolver(settings),
    )
    client = TestClient(app)
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_503_when_backend_unavailable() -> None:
    settings = _settings()
    app = create_app(
        settings=settings,
        backend=BrokenBackend(),
        subject_resolver=fail_closed_subject_resolver(settings),
    )
    client = TestClient(app)
    response = client.get("/readyz")
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == 503
    assert payload["title"] == "Service Unavailable"
    assert "problem+json" in response.headers["content-type"]


def test_version_returns_contract_metadata(tmp_path: Path) -> None:
    settings = _settings()
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=fail_closed_subject_resolver(settings),
    )
    client = TestClient(app)
    response = client.get("/version")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "safecode-enterprise-team-server"
    assert payload["api_version"] == "2.1.0-planned"
    assert payload["contract_status"] == "planned"


def test_server_mode_subject_resolver_fails_closed() -> None:
    settings = TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.SERVER,
            "database_url": "postgresql://user:pass@127.0.0.1:5432/enterprise",
            "oidc_issuer": "https://issuer.example",
            "oidc_audience": "safecode-enterprise",
        }
    )
    resolver = fail_closed_subject_resolver(settings)
    with pytest.raises(Exception, match="authenticated subject required"):
        resolver()
