"""GitHub App credential boundary tests (v2.2.1-T1)."""

from __future__ import annotations

import json

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from safecode.enterprise.api.settings import TeamServerSettings
from safecode.enterprise.connectors.github_app import (
    GitHubAppClient,
    GitHubAppConfigurationError,
    GitHubAppCredentialError,
    GitHubAppSecretLeakError,
    InstallationToken,
    assert_output_safe,
    build_github_app_config,
    reject_project_local_credential_source,
)

APP_ID = "123456"
INSTALLATION_ID = "987654"
WEBHOOK_SECRET = "test-webhook-secret-value"


def _generate_private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def _config(*, private_key_pem: str | None = None) -> object:
    pem = private_key_pem or _generate_private_key_pem()
    return build_github_app_config(
        app_id=APP_ID,
        installation_id=INSTALLATION_ID,
        private_key_pem=SecretStr(pem),
        webhook_secret=SecretStr(WEBHOOK_SECRET),
        webhook_tenant_id="tenant-github",
    )


def test_valid_env_exchanges_installation_token_with_recorded_transport():
    config = _config()
    assert config is not None

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/app/installations/{INSTALLATION_ID}/access_tokens")
        auth = request.headers.get("Authorization", "")
        assert auth.startswith("Bearer ")
        assert "ghp_" not in auth
        return httpx.Response(
            201,
            json={"token": "ghs_recorded_installation_token_value", "expires_at": "2030-01-01T00:00:00Z"},
        )

    client = GitHubAppClient.from_config(config, transport=httpx.MockTransport(handler))
    token = client.exchange_installation_token()
    assert isinstance(token, InstallationToken)
    assert token.token.get_secret_value().startswith("ghs_")
    assert token.expires_at == "2030-01-01T00:00:00Z"


def test_missing_private_key_fails_closed():
    with pytest.raises(GitHubAppConfigurationError, match="partial GitHub App configuration"):
        build_github_app_config(
            app_id=APP_ID,
            installation_id=INSTALLATION_ID,
            private_key_pem=None,
        )


def test_malformed_private_key_fails_closed():
    config = build_github_app_config(
        app_id=APP_ID,
        installation_id=INSTALLATION_ID,
        private_key_pem=SecretStr("not-a-private-key"),
    )
    assert config is not None
    client = GitHubAppClient.from_config(config, transport=httpx.MockTransport(lambda _r: httpx.Response(500)))
    with pytest.raises(GitHubAppCredentialError, match="malformed private key"):
        client.create_app_jwt()


def test_wrong_app_id_installation_exchange_fails_closed():
    config = _config()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    client = GitHubAppClient.from_config(config, transport=httpx.MockTransport(handler))
    with pytest.raises(GitHubAppCredentialError, match="installation not found"):
        client.exchange_installation_token()


def test_secret_values_are_redacted_from_repr():
    pem = _generate_private_key_pem()
    config = build_github_app_config(
        app_id=APP_ID,
        installation_id=INSTALLATION_ID,
        private_key_pem=SecretStr(pem),
        webhook_secret=SecretStr(WEBHOOK_SECRET),
    )
    assert config is not None
    rendered = repr(config)
    assert pem not in rendered
    assert WEBHOOK_SECRET not in rendered
    assert "**********" in rendered

    token = InstallationToken(token=SecretStr("ghs_leaked_token_value"), expires_at="2030-01-01T00:00:00Z")
    token_repr = repr(token)
    assert "ghs_leaked_token_value" not in token_repr


def test_secret_echo_in_captured_output_fails_closed():
    pem = _generate_private_key_pem()
    with pytest.raises(GitHubAppSecretLeakError):
        assert_output_safe(f"debug {pem}", context="log line")
    with pytest.raises(GitHubAppSecretLeakError):
        assert_output_safe("Authorization: Bearer ghp_1234567890123456789012345678901234")


def test_project_local_credential_discovery_fails_closed(tmp_path):
    with pytest.raises(GitHubAppConfigurationError, match="project-local"):
        reject_project_local_credential_source(
            "examples/enterprise/dev/signing-key.pem",
            project_root=tmp_path,
        )
    project_key = tmp_path / "secrets.pem"
    project_key.write_text("BEGIN PRIVATE KEY", encoding="utf-8")
    with pytest.raises(GitHubAppConfigurationError, match="project-local"):
        reject_project_local_credential_source(str(project_key), project_root=tmp_path)


def test_rotation_requires_explicit_reload():
    first_pem = _generate_private_key_pem()
    second_pem = _generate_private_key_pem()
    config = build_github_app_config(
        app_id=APP_ID,
        installation_id=INSTALLATION_ID,
        private_key_pem=SecretStr(first_pem),
    )
    assert config is not None
    client = GitHubAppClient.from_config(config, transport=httpx.MockTransport(lambda _r: httpx.Response(404)))
    first_jwt = client.create_app_jwt()

    rotated = build_github_app_config(
        app_id=APP_ID,
        installation_id=INSTALLATION_ID,
        private_key_pem=SecretStr(second_pem),
    )
    assert rotated is not None
    client.reload_config(rotated)
    second_jwt = client.create_app_jwt()
    assert first_jwt != second_jwt


def test_team_server_settings_github_fields_redacted_in_repr():
    pem = _generate_private_key_pem()
    settings = TeamServerSettings.model_validate(
        {
            "github_app_id": APP_ID,
            "github_installation_id": INSTALLATION_ID,
            "github_private_key_pem": pem,
            "github_webhook_secret": WEBHOOK_SECRET,
        }
    )
    rendered = repr(settings)
    assert pem not in rendered
    assert WEBHOOK_SECRET not in rendered
    assert "**********" in rendered
