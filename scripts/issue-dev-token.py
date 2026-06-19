#!/usr/bin/env python3
"""Issue a disposable development bearer token for the v2.1 Team Server profile."""

from __future__ import annotations

import sys
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[1]
DEV_DIR = ROOT / "examples" / "enterprise" / "dev"
ISSUER = "https://issuer.example"
AUDIENCE = "safecode-enterprise"
KID = "test-key-1"


def main() -> None:
    key_path = DEV_DIR / "signing-key.pem"
    if not key_path.is_file():
        print(f"missing development signing key: {key_path}", file=sys.stderr)
        raise SystemExit(1)
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
