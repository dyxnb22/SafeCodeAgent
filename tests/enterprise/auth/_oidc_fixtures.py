"""Shared OIDC test fixtures for enterprise auth tests."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://issuer.example"
AUDIENCE = "safecode-enterprise"
KID = "test-key-1"


def _int_to_base64url(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).decode("ascii").rstrip("=")


@dataclass(frozen=True)
class OidcTestKeys:
    private_key_pem: bytes
    jwks: dict[str, Any]

    def sign(
        self,
        *,
        sub: str = "user:reviewer",
        tenant_id: str = "tenant-a",
        roles: list[str] | None = None,
        audience: str = AUDIENCE,
        issuer: str = ISSUER,
        expires_in: int = 3600,
        extra_claims: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        now = int(time.time())
        payload: dict[str, Any] = {
            "sub": sub,
            "iss": issuer,
            "aud": audience,
            "exp": now + expires_in,
            "iat": now,
            "tenant_id": tenant_id,
        }
        if roles is not None:
            payload["roles"] = roles
        if extra_claims:
            payload.update(extra_claims)
        token_headers = {"kid": KID, "alg": "RS256"}
        if headers:
            token_headers.update(headers)
        private_key = serialization.load_pem_private_key(self.private_key_pem, password=None)
        return jwt.encode(payload, private_key, algorithm="RS256", headers=token_headers)


def generate_oidc_test_keys() -> OidcTestKeys:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_numbers = private_key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": KID,
                "use": "sig",
                "alg": "RS256",
                "n": _int_to_base64url(public_numbers.n),
                "e": _int_to_base64url(public_numbers.e),
            }
        ]
    }
    return OidcTestKeys(private_key_pem=private_key_pem, jwks=jwks)
