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
