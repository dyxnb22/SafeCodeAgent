#!/usr/bin/env python3
"""Issue a disposable development bearer token for the v2.1 Team Server profile."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
DEV_DIR = ROOT / "compose" / ".enterprise-dev-oidc"
ISSUER = "https://issuer.example"
AUDIENCE = "safecode-enterprise"
KID = "test-key-1"


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def prepare() -> None:
    DEV_DIR.mkdir(parents=True, exist_ok=True)
    key_path = DEV_DIR / "signing-key.pem"
    jwks_path = DEV_DIR / "jwks.json"
    if key_path.is_file() and jwks_path.is_file():
        return
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    numbers = private_key.public_key().public_numbers()
    jwks_path.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "kty": "RSA",
                        "use": "sig",
                        "alg": "RS256",
                        "kid": KID,
                        "n": _b64url_uint(numbers.n),
                        "e": _b64url_uint(numbers.e),
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    prepare()
    if args.prepare:
        return
    key_path = DEV_DIR / "signing-key.pem"
    private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    token = jwt.encode(
        {
            "sub": "user:dev-operator",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": 4_000_000_000,
            "iat": 1_700_000_000,
            "tenant_id": "tenant-dev",
            "roles": ["maintainer"],
        },
        private_key,
        algorithm="RS256",
        headers={"kid": KID, "alg": "RS256"},
    )
    print(token)


if __name__ == "__main__":
    main()
