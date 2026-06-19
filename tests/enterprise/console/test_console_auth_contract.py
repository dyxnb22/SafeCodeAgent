"""Console auth and CORS contract tests (v2.3.1-T1)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.exceptions import SettingsValidationError
from safecode.enterprise.api.settings import (
    DOCUMENTED_ENV_VARS,
    RuntimeMode,
    TeamServerSettings,
    parse_cors_allowed_origins,
)
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role


def test_cors_allowed_origins_env_is_documented() -> None:
    assert "SAC_ENTERPRISE_CORS_ALLOWED_ORIGINS" in DOCUMENTED_ENV_VARS


def test_cors_wildcard_origin_fails_closed() -> None:
    with pytest.raises(SettingsValidationError, match="wildcard"):
        parse_cors_allowed_origins("*")


def test_cors_explicit_origins_are_parsed() -> None:
    origins = parse_cors_allowed_origins("http://127.0.0.1:3000,http://localhost:3000/")
    assert origins == ("http://127.0.0.1:3000", "http://localhost:3000")


def test_create_app_registers_cors_for_console_dev_origin(tmp_path) -> None:
    settings = TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.LOCAL,
            "operator_actor": "user:dev",
            "cors_allowed_origins": "http://127.0.0.1:3000",
        }
    )
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=lambda: RBACSubject(actor_id="user:dev", tenant_id="tenant-a", roles=(Role.developer,)),
    )
    client = TestClient(app)
    response = client.options(
        "/v2/runs",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"


def test_console_session_storage_key_is_stable() -> None:
    from pathlib import Path

    session_module = Path(__file__).resolve().parents[3] / "console" / "src" / "lib" / "auth" / "session.ts"
    text = session_module.read_text(encoding="utf-8")
    assert "safecode-console-session" in text
