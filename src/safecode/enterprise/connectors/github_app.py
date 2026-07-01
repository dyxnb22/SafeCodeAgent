"""GitHub App credential boundary and installation token exchange (v2.2.1-T1, D24).

中文模块说明：GitHub App 凭证边界，从环境/密钥库加载，禁止写入仓库。
- 架构位置：Integration 平面身份层；live GitHub 读写的 token 来源。
- 安全不变量：私钥不落库；token 缓存带 TTL；rate limit 耗尽 fail-closed。
- 学习路径：读 ``SECURITY.md`` 与 ``test_github_app_credentials.py``。
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import jwt
from jwt.exceptions import PyJWTError
from pydantic import BaseModel, ConfigDict, SecretStr

from safecode.context.redactor import redact_secrets

APP_JWT_LIFETIME_SECONDS = 600
MAX_WEBHOOK_BODY_BYTES = 256 * 1024

_GH_TOKEN_RE = re.compile(r"gh[psur]_[A-Za-z0-9]{20,}")
_PRIVATE_KEY_MARKERS = ("BEGIN RSA PRIVATE KEY", "BEGIN PRIVATE KEY", "BEGIN EC PRIVATE KEY")
_PROJECT_KEY_PATH_RE = re.compile(r"^(?:\.?/)?(?:examples|tests|compose|\.agents)/", re.IGNORECASE)


class GitHubAppError(Exception):
    """Base GitHub App error."""


class GitHubAppCredentialError(GitHubAppError):
    """Raised when GitHub App credentials are missing or invalid."""


class GitHubAppConfigurationError(GitHubAppCredentialError):
    """Raised when GitHub App configuration is incomplete or unsafe."""


class GitHubAppSecretLeakError(GitHubAppCredentialError):
    """Raised when secret material would leak into captured output."""


class GitHubWebhookError(GitHubAppError):
    """Raised when webhook validation fails."""


def secret_repr(value: SecretStr | None) -> str:
    if value is None:
        return "None"
    return "SecretStr('**********')"


def assert_output_safe(text: str, *, context: str = "output") -> None:
    """Fail closed when secret material appears in captured output."""
    for marker in _PRIVATE_KEY_MARKERS:
        if marker in text:
            raise GitHubAppSecretLeakError(f"{context} contains private key material")
    if _GH_TOKEN_RE.search(text):
        raise GitHubAppSecretLeakError(f"{context} contains GitHub token material")


class GitHubAppConfig(BaseModel):
    """Frozen GitHub App credentials loaded from environment or vault only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    app_id: str
    installation_id: str
    private_key_pem: SecretStr
    webhook_secret: SecretStr | None = None
    webhook_tenant_id: str = "github"
    api_base_url: str = "https://api.github.com"

    def __repr__(self) -> str:
        return (
            "GitHubAppConfig("
            f"app_id={self.app_id!r}, "
            f"installation_id={self.installation_id!r}, "
            f"private_key_pem={secret_repr(self.private_key_pem)}, "
            f"webhook_secret={secret_repr(self.webhook_secret)}, "
            f"webhook_tenant_id={self.webhook_tenant_id!r}, "
            f"api_base_url={self.api_base_url!r})"
        )


class InstallationToken(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    token: SecretStr
    expires_at: str

    def __repr__(self) -> str:
        return (
            "InstallationToken("
            f"token={secret_repr(self.token)}, "
            f"expires_at={self.expires_at!r})"
        )


def reject_project_local_credential_source(value: str, *, project_root: Path | None = None) -> None:
    """Fail closed when credentials appear to be loaded from repository paths."""
    normalized = value.strip()
    if not normalized:
        return
    if _PROJECT_KEY_PATH_RE.match(normalized):
        raise GitHubAppConfigurationError("project-local credential paths are not allowed")
    if project_root is not None:
        candidate = Path(normalized)
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        root = project_root.resolve()
        try:
            candidate.relative_to(root)
            if candidate.suffix in {".pem", ".key", ".env"} or candidate.name in {
                "jwks.json",
                "signing-key.pem",
            }:
                raise GitHubAppConfigurationError("project-local credential files are not allowed")
        except ValueError:
            pass


def build_github_app_config(
    *,
    app_id: str | None,
    installation_id: str | None,
    private_key_pem: SecretStr | None,
    webhook_secret: SecretStr | None = None,
    webhook_tenant_id: str | None = None,
    api_base_url: str | None = None,
    project_root: Path | None = None,
) -> GitHubAppConfig | None:
    """Build GitHub App config when fully specified; fail closed on partial config."""
    values = {
        "app_id": (app_id or "").strip(),
        "installation_id": (installation_id or "").strip(),
        "private_key_pem": private_key_pem,
        "webhook_secret": webhook_secret,
    }
    provided = [name for name, value in values.items() if value]
    if not provided:
        return None
    missing = [name for name, value in values.items() if name != "webhook_secret" and not value]
    if missing:
        raise GitHubAppConfigurationError(
            "partial GitHub App configuration is not allowed: "
            + ", ".join(missing)
        )
    assert private_key_pem is not None
    key_material = private_key_pem.get_secret_value()
    reject_project_local_credential_source(key_material, project_root=project_root)
    if webhook_secret is not None:
        reject_project_local_credential_source(
            webhook_secret.get_secret_value(),
            project_root=project_root,
        )
    return GitHubAppConfig(
        app_id=values["app_id"],
        installation_id=values["installation_id"],
        private_key_pem=private_key_pem,
        webhook_secret=webhook_secret,
        webhook_tenant_id=(webhook_tenant_id or "github").strip() or "github",
        api_base_url=(api_base_url or "https://api.github.com").strip(),
    )


@dataclass
class GitHubAppClient:
    """Exchange installation tokens using recorded or live HTTP transport."""

    _config: GitHubAppConfig
    _transport: httpx.BaseTransport | None = field(default=None, repr=False)
    _http_client: httpx.Client | None = field(default=None, repr=False)

    @classmethod
    def from_config(
        cls,
        config: GitHubAppConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> GitHubAppClient:
        return cls(config, transport)

    @property
    def config(self) -> GitHubAppConfig:
        return self._config

    def reload_config(self, config: GitHubAppConfig) -> None:
        """Rotation requires explicit reload; credentials are not auto-refreshed."""
        self._config = config
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def __repr__(self) -> str:
        return f"GitHubAppClient(config={self._config!r})"

    def _http(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(
                transport=self._transport,
                base_url=self._config.api_base_url.rstrip("/"),
                timeout=30.0,
            )
        return self._http_client

    def create_app_jwt(self) -> str:
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + APP_JWT_LIFETIME_SECONDS,
            "iss": self._config.app_id,
        }
        private_key = self._config.private_key_pem.get_secret_value()
        try:
            return jwt.encode(payload, private_key, algorithm="RS256")
        except (PyJWTError, ValueError, TypeError) as exc:
            raise GitHubAppCredentialError("malformed private key") from exc

    def exchange_installation_token(self, *, installation_id: str | None = None) -> InstallationToken:
        installation = (installation_id or self._config.installation_id).strip()
        if not installation:
            raise GitHubAppConfigurationError("installation_id is required")
        app_jwt = self.create_app_jwt()
        response = self._http().post(
            f"/app/installations/{installation}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
            },
        )
        if response.status_code == 404:
            raise GitHubAppCredentialError("installation not found or app id mismatch")
        if response.status_code >= 400:
            detail = redact_secrets(response.text[:512])
            raise GitHubAppCredentialError(
                f"installation token exchange failed ({response.status_code}): {detail}"
            )
        payload = response.json()
        token_value = payload.get("token")
        if not token_value:
            raise GitHubAppCredentialError("installation token exchange returned no token")
        expires_at = str(payload.get("expires_at", ""))
        return InstallationToken(token=SecretStr(str(token_value)), expires_at=expires_at)


def verify_webhook_signature(
    *,
    body: bytes,
    secret: SecretStr,
    signature_header: str | None,
) -> None:
    """Validate GitHub webhook signature against the raw request body."""
    if signature_header is None or not signature_header.startswith("sha256="):
        raise GitHubWebhookError("missing or invalid webhook signature")
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise GitHubWebhookError("webhook body exceeds size limit")
    expected = hmac.new(
        secret.get_secret_value().encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    if not hmac.compare_digest(expected, provided):
        raise GitHubWebhookError("webhook signature mismatch")


def sign_webhook_body(body: bytes, *, secret: str) -> str:
    """Test helper to produce a valid X-Hub-Signature-256 header."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def parse_webhook_event(payload: dict[str, Any]) -> tuple[str, str, int, str]:
    """Extract action, repository, PR number, and installation id from a pull_request event."""
    action = str(payload.get("action", "")).strip()
    installation_raw = payload.get("installation") or {}
    installation_id = str(installation_raw.get("id", "")).strip()
    repository = payload.get("repository") or {}
    repo_full_name = str(repository.get("full_name", "")).strip()
    pull_request = payload.get("pull_request") or {}
    pr_number = int(pull_request.get("number") or 0)
    if not action or not installation_id or not repo_full_name or pr_number <= 0:
        raise GitHubWebhookError("unsupported or malformed webhook payload")
    return action, repo_full_name, pr_number, installation_id
