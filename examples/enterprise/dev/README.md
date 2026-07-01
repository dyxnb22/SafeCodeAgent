# Development-only OIDC material

`bash scripts/enterprise-dev-up.sh` prepares OIDC material, starts the Docker
dev stack, and prints a console bearer token.

`scripts/issue-dev-token.py --prepare` alone generates an ephemeral key pair
under the gitignored `compose/.enterprise-dev-oidc/` directory. No private key
is committed. Delete that directory to rotate the local development identity.
