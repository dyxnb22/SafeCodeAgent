"""Team Server settings contract tests (v2.1.1-T2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from safecode.enterprise.api.exceptions import SettingsValidationError, TeamServerDependencyError
from safecode.enterprise.api.settings import (
    DOCUMENTED_ENV_VARS,
    RuntimeMode,
    TeamServerSettings,
    load_team_server_settings,
    load_team_server_settings_from_env,
)

_SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "settings_env.json"
_SECRET_DSN = "postgresql://svc:super-secret-password@db.example:5432/enterprise"


def test_documented_env_vars_snapshot() -> None:
    expected = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    live = {
        "env_prefix": "SAC_ENTERPRISE_",
        "variables": list(DOCUMENTED_ENV_VARS),
    }
    assert live == expected


def test_local_defaults_are_deterministic() -> None:
    settings = load_team_server_settings()
    assert settings.runtime_mode is RuntimeMode.LOCAL
    assert settings.database_url is None
    assert settings.oidc_issuer is None
    assert settings.oidc_audience is None
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8080
    assert settings.server_url is None
    assert settings.operator_actor is None


def test_complete_server_settings_validate_without_network() -> None:
    settings = load_team_server_settings(
        runtime_mode=RuntimeMode.SERVER,
        database_url=_SECRET_DSN,
        oidc_issuer="https://issuer.example/",
        oidc_audience="safecode-enterprise",
        server_url="https://team.example/v2",
    )
    assert settings.runtime_mode is RuntimeMode.SERVER
    assert settings.database_url is not None
    assert settings.database_url.get_secret_value() == _SECRET_DSN


@pytest.mark.parametrize("missing_field", ("database_url", "oidc_issuer", "oidc_audience"))
def test_server_mode_missing_required_fields_fail_closed(missing_field: str) -> None:
    payload = {
        "runtime_mode": RuntimeMode.SERVER,
        "database_url": _SECRET_DSN,
        "oidc_issuer": "https://issuer.example/",
        "oidc_audience": "safecode-enterprise",
    }
    payload[missing_field] = None
    with pytest.raises(SettingsValidationError, match=missing_field):
        load_team_server_settings(**payload)


def test_unknown_runtime_mode_fails_closed() -> None:
    with pytest.raises(SettingsValidationError):
        load_team_server_settings(runtime_mode="hybrid")


def test_local_operator_actor_rejected_in_server_mode() -> None:
    with pytest.raises(SettingsValidationError, match="operator_actor"):
        load_team_server_settings(
            runtime_mode=RuntimeMode.SERVER,
            database_url=_SECRET_DSN,
            oidc_issuer="https://issuer.example/",
            oidc_audience="safecode-enterprise",
            operator_actor="alice",
        )


def test_local_mode_allows_operator_actor() -> None:
    settings = load_team_server_settings(operator_actor="alice")
    assert settings.operator_actor == "alice"


def test_secret_values_are_redacted_from_repr_and_validation_text() -> None:
    settings = load_team_server_settings(database_url=_SECRET_DSN)
    rendered = repr(settings)
    assert _SECRET_DSN not in rendered
    assert "super-secret-password" not in rendered
    assert "**********" in rendered

    with pytest.raises(SettingsValidationError) as excinfo:
        load_team_server_settings(
            runtime_mode=RuntimeMode.SERVER,
            database_url=_SECRET_DSN,
            oidc_issuer="https://issuer.example/",
            oidc_audience="",
        )
    message = str(excinfo.value)
    assert _SECRET_DSN not in message
    assert "super-secret-password" not in message


def test_settings_import_does_not_eagerly_load_pydantic_settings() -> None:
    before = set(sys.modules)
    import safecode.enterprise.api.settings as settings_module  # noqa: F401

    loaded = set(sys.modules) - before
    assert not any(name == "pydantic_settings" or name.startswith("pydantic_settings.") for name in loaded)


def test_load_from_env_requires_team_server_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    import safecode.enterprise.api.settings as settings_module

    def _missing() -> None:
        raise ImportError("blocked for test")

    monkeypatch.setattr(settings_module, "_import_pydantic_settings", _missing)
    with pytest.raises(TeamServerDependencyError, match="team-server"):
        load_team_server_settings_from_env()


def test_load_from_env_uses_documented_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("pydantic_settings")
    monkeypatch.setenv("SAC_ENTERPRISE_RUNTIME_MODE", "server")
    monkeypatch.setenv("SAC_ENTERPRISE_DATABASE_URL", _SECRET_DSN)
    monkeypatch.setenv("SAC_ENTERPRISE_OIDC_ISSUER", "https://issuer.example/")
    monkeypatch.setenv("SAC_ENTERPRISE_OIDC_AUDIENCE", "safecode-enterprise")
    monkeypatch.setenv("SAC_ENTERPRISE_API_HOST", "0.0.0.0")
    monkeypatch.setenv("SAC_ENTERPRISE_API_PORT", "9000")
    monkeypatch.setenv("SAC_ENTERPRISE_SERVER_URL", "https://team.example/v2")

    settings = load_team_server_settings_from_env()
    assert settings.runtime_mode is RuntimeMode.SERVER
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 9000
    assert settings.server_url == "https://team.example/v2"


def test_team_server_settings_model_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TeamServerSettings.model_validate({"unexpected": True})
