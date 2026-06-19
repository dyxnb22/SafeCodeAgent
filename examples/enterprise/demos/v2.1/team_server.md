# v2.1 Team Server Demo

## Goal

Demonstrate the frozen v2.1 Team Server surface: authenticated API commands,
worker execution, contract snapshots, and the disposable Compose development
profile.

## Contract gate

```bash
PYTHONPATH=src python3 -m pytest -q tests/enterprise/contracts
PYTHONPATH=src python3 -m pytest -q tests/enterprise/api/test_integration_v2_1.py -m "not postgres_integration"
```

## Local CLI fallback (no auth)

```bash
sac enterprise workflow run \
  --task pr_review \
  --input examples/enterprise/fixtures/pr_sql_injection \
  --root .
```

## Server mode against the dev Compose profile

```bash
./scripts/run-enterprise-dev.sh
export SAFECODE_ENTERPRISE_TOKEN="$(uv run python scripts/issue-dev-token.py)"
sac enterprise workflow run \
  --task pr_review \
  --input examples/enterprise/fixtures/pr_sql_injection \
  --root . \
  --tenant tenant-dev \
  --server-url http://127.0.0.1:8080
```

## Upgrade / rollback rehearsal (disposable volumes)

```bash
# Apply schema on a fresh PostgreSQL volume
./scripts/run-enterprise-dev.sh

# Tear down and discard dev state
docker compose -f compose.enterprise.yaml down -v
```

Local mode remains the documented fallback when Docker or OIDC dev credentials
are unavailable.

## Acceptance checklist

| Gate | Command | Expected |
|------|---------|----------|
| v2.1 contract snapshot | `tests/enterprise/contracts/test_public_contract_v2_1.py` | Green |
| Offline integration | `tests/enterprise/api/test_integration_v2_1.py` | Green |
| Compose validation | `tests/enterprise/deploy/test_compose_enterprise.py` | Green |
| PostgreSQL lane | `./scripts/run-postgres-integration.sh` | Green when Docker available |
