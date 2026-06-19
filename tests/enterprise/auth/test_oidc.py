"""OIDC JWT validation tests (v2.1.6-T1)."""

from __future__ import annotations

import jwt
import pytest

from safecode.enterprise.auth.oidc import (
    JwksKeyCache,
    OidcValidator,
    StaticJwksProvider,
    TokenValidationError,
    build_oidc_validator,
    load_oidc_discovery,
)
from oidc_fixtures import AUDIENCE, ISSUER, generate_oidc_test_keys


def test_valid_token_resolves_to_claims_object() -> None:
    keys = generate_oidc_test_keys()
    validator = build_oidc_validator(issuer=ISSUER, audience=AUDIENCE, jwks=keys.jwks)
    token = keys.sign(sub="user:alice", tenant_id="tenant-a", roles=["developer"])

    claims = validator.validate_token(token)

    assert claims.sub == "user:alice"
    assert claims.tenant_id == "tenant-a"
    assert list(claims.roles or []) == ["developer"]


def test_expired_token_is_rejected() -> None:
    keys = generate_oidc_test_keys()
    validator = build_oidc_validator(issuer=ISSUER, audience=AUDIENCE, jwks=keys.jwks)
    token = keys.sign(expires_in=-120)

    with pytest.raises(TokenValidationError, match="expired|Expired|Signature has expired"):
        validator.validate_token(token)


def test_wrong_audience_is_rejected() -> None:
    keys = generate_oidc_test_keys()
    validator = build_oidc_validator(issuer=ISSUER, audience=AUDIENCE, jwks=keys.jwks)
    token = keys.sign(audience="other-audience")

    with pytest.raises(TokenValidationError):
        validator.validate_token(token)


def test_tampered_token_is_rejected() -> None:
    keys = generate_oidc_test_keys()
    validator = build_oidc_validator(issuer=ISSUER, audience=AUDIENCE, jwks=keys.jwks)
    token = keys.sign()
    header, payload, _signature = token.split(".")
    tampered = f"{header}.{payload}.invalid-signature"

    with pytest.raises(TokenValidationError):
        validator.validate_token(tampered)


def test_disallowed_algorithm_is_rejected() -> None:
    keys = generate_oidc_test_keys()
    validator = build_oidc_validator(issuer=ISSUER, audience=AUDIENCE, jwks=keys.jwks)
    now = int(__import__("time").time())
    token = jwt.encode(
        {
            "sub": "user:alice",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": now + 3600,
            "iat": now,
        },
        "symmetric-secret",
        algorithm="HS256",
        headers={"kid": "test-key-1", "alg": "HS256"},
    )

    with pytest.raises(TokenValidationError, match="not allowed"):
        validator.validate_token(token)


def test_jwks_cache_reuses_signing_key() -> None:
    keys = generate_oidc_test_keys()
    cache = JwksKeyCache(ttl_seconds=300)
    provider = StaticJwksProvider(keys.jwks, cache=cache)
    validator = OidcValidator(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_provider=provider,
    )
    token = keys.sign()
    validator.validate_token(token)
    assert cache.get("test-key-1") is not None
    validator.validate_token(token)


def test_load_oidc_discovery_uses_injected_fetch() -> None:
    discovery = load_oidc_discovery(
        ISSUER,
        fetch_json=lambda _url: {
            "issuer": ISSUER,
            "jwks_uri": "https://issuer.example/jwks",
        },
    )
    assert discovery.issuer == ISSUER
    assert discovery.jwks_uri == "https://issuer.example/jwks"


def test_clock_skew_allows_recent_expiry() -> None:
    keys = generate_oidc_test_keys()
    validator = build_oidc_validator(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks=keys.jwks,
        clock_skew_seconds=120,
    )
    token = keys.sign(expires_in=-30)

    claims = validator.validate_token(token)
    assert claims.sub == "user:reviewer"
