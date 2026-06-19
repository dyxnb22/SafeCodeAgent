# v2.3 Operator Console Demo

## Goal

Demonstrate the v2.3 Operator Console against the v2.1 Team Server API: run list
and detail, redacted trace viewing, approval inbox, evidence export, and eval
baseline visibility.

## Contract gate

```bash
PYTHONPATH=src python3 -m pytest -q tests/enterprise/contracts/test_public_contract_v2_3.py
PYTHONPATH=src python3 -m pytest -q tests/enterprise/console -m "not live_oidc"
cd console && npm test
```

## Start Team Server (Compose)

```bash
./scripts/run-enterprise-dev.sh
```

Optional console service (when enabled in `compose.enterprise.yaml`):

```bash
docker compose -f compose.enterprise.yaml up console
```

## Start console locally

```bash
cd console
npm install
NEXT_PUBLIC_SAC_API_BASE_URL=http://127.0.0.1:8080 npm run dev
```

Sign in through `/login` with a dev OIDC token whose claims include the target
tenant. Navigate to `/t/{tenantId}/runs` for the run list.

## Operator walkthrough

| Surface | Route | Expected |
|---------|-------|----------|
| Run list | `/t/{tenantId}/runs` | Tenant-scoped rows from `/v2/runs` |
| Run detail | `/t/{tenantId}/runs/{runId}` | Timeline + trace tabs, strict redaction |
| Approvals | `/t/{tenantId}/approvals` | Pending inbox; decide via `Idempotency-Key` |
| Evidence | `/t/{tenantId}/runs/{runId}/evidence` | Read-only zip export |
| Eval | `/t/{tenantId}/eval` | Read-only baseline list |

## Acceptance checklist

| Gate | Command | Expected |
|------|---------|----------|
| v2.3 UI contract | `tests/enterprise/contracts/test_public_contract_v2_3.py` | Green |
| Console offline suites | `tests/enterprise/console` | Green excluding `live_oidc` |
| Console unit tests | `cd console && npm test` | Green |

Local CLI mode remains the documented fallback when Docker, OIDC, or the console
dev server are unavailable.
