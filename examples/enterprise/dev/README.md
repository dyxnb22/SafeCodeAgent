# Development-only OIDC material

`scripts/issue-dev-token.py --prepare` generates an ephemeral key pair under
the gitignored `compose/.enterprise-dev-oidc/` directory. No private key is
committed. Delete that directory to rotate the local development identity.
