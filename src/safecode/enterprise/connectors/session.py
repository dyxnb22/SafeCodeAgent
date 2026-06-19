"""Optional connector session overrides for recorded transports (v2.2.5)."""

from __future__ import annotations

from contextvars import ContextVar, Token

import httpx
from pydantic import SecretStr

_github_transport: ContextVar[httpx.BaseTransport | None] = ContextVar(
    "github_transport",
    default=None,
)
_github_access_token: ContextVar[SecretStr | None] = ContextVar(
    "github_access_token",
    default=None,
)


def get_github_transport() -> httpx.BaseTransport | None:
    return _github_transport.get()


def set_github_transport(transport: httpx.BaseTransport | None) -> Token[httpx.BaseTransport | None]:
    return _github_transport.set(transport)


def reset_github_transport(token: Token[httpx.BaseTransport | None]) -> None:
    _github_transport.reset(token)


def get_github_access_token() -> SecretStr | None:
    return _github_access_token.get()


def set_github_access_token(token: SecretStr | None) -> Token[SecretStr | None]:
    return _github_access_token.set(token)


def reset_github_access_token(token: Token[SecretStr | None]) -> None:
    _github_access_token.reset(token)


_jira_transport: ContextVar[httpx.BaseTransport | None] = ContextVar(
    "jira_transport",
    default=None,
)
_jira_email: ContextVar[str | None] = ContextVar("jira_email", default=None)
_jira_api_token: ContextVar[SecretStr | None] = ContextVar("jira_api_token", default=None)


def get_jira_transport() -> httpx.BaseTransport | None:
    return _jira_transport.get()


def set_jira_transport(transport: httpx.BaseTransport | None) -> Token[httpx.BaseTransport | None]:
    return _jira_transport.set(transport)


def reset_jira_transport(token: Token[httpx.BaseTransport | None]) -> None:
    _jira_transport.reset(token)


def get_jira_email() -> str | None:
    return _jira_email.get()


def set_jira_email(email: str | None) -> Token[str | None]:
    return _jira_email.set(email)


def reset_jira_email(token: Token[str | None]) -> None:
    _jira_email.reset(token)


def get_jira_api_token() -> SecretStr | None:
    return _jira_api_token.get()


def set_jira_api_token(token: SecretStr | None) -> Token[SecretStr | None]:
    return _jira_api_token.set(token)


def reset_jira_api_token(token: Token[SecretStr | None]) -> None:
    _jira_api_token.reset(token)
