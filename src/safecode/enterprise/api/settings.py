"""Runtime mode and Team Server settings contracts (D22)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator

from safecode.enterprise.api.exceptions import SettingsValidationError, TeamServerDependencyError

ENV_PREFIX: Final[str] = "SAC_ENTERPRISE_"


class RuntimeMode(str, Enum):
    LOCAL = "local"
    SERVER = "server"


DOCUMENTED_ENV_VARS: Final[tuple[str, ...]] = (
    f"{ENV_PREFIX}RUNTIME_MODE",
    f"{ENV_PREFIX}DATABASE_URL",
    f"{ENV_PREFIX}OIDC_ISSUER",
    f"{ENV_PREFIX}OIDC_AUDIENCE",
    f"{ENV_PREFIX}OIDC_JWKS_PATH",
    f"{ENV_PREFIX}API_HOST",
    f"{ENV_PREFIX}API_PORT",
    f"{ENV_PREFIX}SERVER_URL",
    f"{ENV_PREFIX}OPERATOR_ACTOR",
    f"{ENV_PREFIX}GITHUB_APP_ID",
    f"{ENV_PREFIX}GITHUB_INSTALLATION_ID",
    f"{ENV_PREFIX}GITHUB_PRIVATE_KEY_PEM",
    f"{ENV_PREFIX}GITHUB_WEBHOOK_SECRET",
    f"{ENV_PREFIX}GITHUB_WEBHOOK_TENANT_ID",
    f"{ENV_PREFIX}GITHUB_API_BASE_URL",
)


class TeamServerSettings(BaseModel):
    """Typed local/server configuration without live discovery or connections."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_mode: RuntimeMode = RuntimeMode.LOCAL
    database_url: SecretStr | None = None
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_path: str | None = None
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8080, ge=1, le=65535)
    server_url: str | None = None
    operator_actor: str | None = None
    github_app_id: str | None = None
    github_installation_id: str | None = None
    github_private_key_pem: SecretStr | None = None
    github_webhook_secret: SecretStr | None = None
    github_webhook_tenant_id: str | None = None
    github_api_base_url: str | None = None

    @field_validator(
        "oidc_issuer",
        "oidc_audience",
        "oidc_jwks_path",
        "server_url",
        "operator_actor",
        "github_app_id",
        "github_installation_id",
        "github_webhook_tenant_id",
        "github_api_base_url",
    )
    @classmethod
    def _strip_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _validate_mode_requirements(self) -> TeamServerSettings:
        if self.runtime_mode is RuntimeMode.SERVER:
            missing: list[str] = []
            if self.database_url is None:
                missing.append("database_url")
            if not self.oidc_issuer:
                missing.append("oidc_issuer")
            if not self.oidc_audience:
                missing.append("oidc_audience")
            if missing:
                raise SettingsValidationError(
                    "server mode requires explicit configuration: "
                    + ", ".join(missing)
                )
            if self.operator_actor:
                raise SettingsValidationError(
                    "operator_actor is allowed in local mode only"
                )
        return self

    def __repr__(self) -> str:
        return (
            "TeamServerSettings("
            f"runtime_mode={self.runtime_mode.value!r}, "
            f"database_url={self._secret_repr(self.database_url)}, "
            f"oidc_issuer={self.oidc_issuer!r}, "
            f"oidc_audience={self.oidc_audience!r}, "
            f"oidc_jwks_path={self.oidc_jwks_path!r}, "
            f"api_host={self.api_host!r}, "
            f"api_port={self.api_port}, "
            f"server_url={self.server_url!r}, "
            f"operator_actor={self.operator_actor!r}, "
            f"github_app_id={self.github_app_id!r}, "
            f"github_installation_id={self.github_installation_id!r}, "
            f"github_private_key_pem={self._secret_repr(self.github_private_key_pem)}, "
            f"github_webhook_secret={self._secret_repr(self.github_webhook_secret)}, "
            f"github_webhook_tenant_id={self.github_webhook_tenant_id!r}, "
            f"github_api_base_url={self.github_api_base_url!r})"
        )

    @staticmethod
    def _secret_repr(value: SecretStr | None) -> str:
        if value is None:
            return "None"
        return "SecretStr('**********')"


def _import_pydantic_settings():  # pragma: no cover - exercised via monkeypatch in tests
    from pydantic_settings import BaseSettings, SettingsConfigDict

    return BaseSettings, SettingsConfigDict


def load_team_server_settings(**overrides: Any) -> TeamServerSettings:
    """Load settings from explicit values (deterministic tests and callers)."""
    try:
        return TeamServerSettings.model_validate(overrides)
    except SettingsValidationError:
        raise
    except ValidationError as exc:
        raise SettingsValidationError(str(exc)) from exc


def load_team_server_settings_from_env() -> TeamServerSettings:
    """Load settings from SAC_ENTERPRISE_* environment variables."""
    try:
        BaseSettings, SettingsConfigDict = _import_pydantic_settings()
    except ImportError as exc:
        raise TeamServerDependencyError(
            "team-server optional extra is required to load settings from the environment; "
            "install safecode-agent[team-server]"
        ) from exc

    class _EnvTeamServerSettings(BaseSettings):
        model_config = SettingsConfigDict(
            env_prefix=ENV_PREFIX,
            extra="forbid",
            case_sensitive=False,
        )

        runtime_mode: RuntimeMode = RuntimeMode.LOCAL
        database_url: SecretStr | None = None
        oidc_issuer: str | None = None
        oidc_audience: str | None = None
        oidc_jwks_path: str | None = None
        api_host: str = "127.0.0.1"
        api_port: int = Field(default=8080, ge=1, le=65535)
        server_url: str | None = None
        operator_actor: str | None = None
        github_app_id: str | None = None
        github_installation_id: str | None = None
        github_private_key_pem: SecretStr | None = None
        github_webhook_secret: SecretStr | None = None
        github_webhook_tenant_id: str | None = None
        github_api_base_url: str | None = None

    try:
        env_values = _EnvTeamServerSettings().model_dump()
        return load_team_server_settings(**env_values)
    except SettingsValidationError:
        raise
    except Exception as exc:
        message = str(exc)
        if "database_url" in message.lower() and "secret" in message.lower():
            message = "invalid team server settings"
        raise SettingsValidationError(message) from exc
