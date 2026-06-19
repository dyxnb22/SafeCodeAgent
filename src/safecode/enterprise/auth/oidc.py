"""OIDC discovery and JWT validation for the Team Server (v2.1.6-T1)."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ConfigDict

DEFAULT_ALLOWED_ALGORITHMS: tuple[str, ...] = ("RS256",)
DEFAULT_CLOCK_SKEW_SECONDS = 60
DEFAULT_JWKS_CACHE_TTL_SECONDS = 300


class TokenValidationError(Exception):
    """Raised when a bearer token fails cryptographic or claim validation."""


class TokenClaims(BaseModel):
    """Validated OIDC token claims used for subject mapping."""

    model_config = ConfigDict(extra="allow", frozen=True)

    sub: str
    iss: str
    aud: str | list[str]
    exp: int
    iat: int | None = None
    tenant_id: str | None = None
    role: str | None = None
    roles: tuple[str, ...] | list[str] | None = None


@dataclass(frozen=True)
class OidcDiscoveryConfig:
    issuer: str
    jwks_uri: str


class JwksKeyCache:
    """Small in-memory JWKS cache with bounded TTL."""

    def __init__(self, *, ttl_seconds: int = DEFAULT_JWKS_CACHE_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, kid: str) -> Any | None:
        entry = self._entries.get(kid)
        if entry is None:
            return None
        expires_at, key = entry
        if time.monotonic() >= expires_at:
            self._entries.pop(kid, None)
            return None
        return key

    def set(self, kid: str, key: Any) -> None:
        self._entries[kid] = (time.monotonic() + self._ttl_seconds, key)


class StaticJwksProvider:
    """Resolve signing keys from a fixed JWKS document without network I/O."""

    def __init__(
        self,
        jwks: Mapping[str, Any],
        *,
        cache: JwksKeyCache | None = None,
        allowed_algorithms: tuple[str, ...] = DEFAULT_ALLOWED_ALGORITHMS,
    ) -> None:
        self._cache = cache or JwksKeyCache()
        self._allowed_algorithms = allowed_algorithms
        self._keys_by_kid: dict[str, Any] = {}
        for entry in jwks.get("keys", []):
            if not isinstance(entry, dict):
                continue
            kid = entry.get("kid")
            if not isinstance(kid, str) or not kid:
                continue
            self._keys_by_kid[kid] = jwt.algorithms.RSAAlgorithm.from_jwk(entry)

    def get_signing_key(self, token: str) -> Any:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        if algorithm not in self._allowed_algorithms:
            raise TokenValidationError(f"algorithm {algorithm!r} is not allowed")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise TokenValidationError("token header missing kid")
        cached = self._cache.get(kid)
        if cached is not None:
            return cached
        key = self._keys_by_kid.get(kid)
        if key is None:
            raise TokenValidationError(f"unknown signing key kid={kid!r}")
        self._cache.set(kid, key)
        return key


class OidcValidator:
    """Validate bearer tokens against configured issuer, audience, and JWKS."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_provider: StaticJwksProvider,
        allowed_algorithms: tuple[str, ...] = DEFAULT_ALLOWED_ALGORITHMS,
        clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_provider = jwks_provider
        self._allowed_algorithms = allowed_algorithms
        self._clock_skew_seconds = clock_skew_seconds

    def validate_token(self, token: str) -> TokenClaims:
        normalized = token.strip()
        if not normalized:
            raise TokenValidationError("empty bearer token")
        try:
            signing_key = self._jwks_provider.get_signing_key(normalized)
            payload = jwt.decode(
                normalized,
                signing_key,
                algorithms=list(self._allowed_algorithms),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._clock_skew_seconds,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        except TokenValidationError:
            raise
        except InvalidTokenError as exc:
            raise TokenValidationError(str(exc)) from exc
        return TokenClaims.model_validate(payload)


def load_oidc_discovery(
    issuer: str,
    *,
    fetch_json: Callable[[str], Mapping[str, Any]],
) -> OidcDiscoveryConfig:
    """Load OIDC discovery metadata using an injected fetch function."""
    discovery_url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    document = fetch_json(discovery_url)
    discovered_issuer = document.get("issuer")
    jwks_uri = document.get("jwks_uri")
    if discovered_issuer != issuer:
        raise TokenValidationError("discovery issuer does not match configured issuer")
    if not isinstance(jwks_uri, str) or not jwks_uri.strip():
        raise TokenValidationError("discovery document missing jwks_uri")
    return OidcDiscoveryConfig(issuer=issuer, jwks_uri=jwks_uri.strip())


def build_oidc_validator(
    *,
    issuer: str,
    audience: str,
    jwks: Mapping[str, Any],
    allowed_algorithms: tuple[str, ...] = DEFAULT_ALLOWED_ALGORITHMS,
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
) -> OidcValidator:
    provider = StaticJwksProvider(jwks, allowed_algorithms=allowed_algorithms)
    return OidcValidator(
        issuer=issuer,
        audience=audience,
        jwks_provider=provider,
        allowed_algorithms=allowed_algorithms,
        clock_skew_seconds=clock_skew_seconds,
    )
