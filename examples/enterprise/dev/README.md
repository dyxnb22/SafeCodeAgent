# Development-only OIDC material for the v2.1 Compose profile.

- `jwks.json` is the public JWKS document mounted by the API.
- `signing-key.pem` is a disposable development private key used only by
  `scripts/issue-dev-token.py`.
- Do not reuse these credentials outside local development.
