# Enterprise Deployment Profiles

SafeCodeAgent Enterprise supports the same safety contracts in local and Team
Server modes. A profile changes identity, persistence, and operational
ownership; it does not weaken policy, approval, audit, or redaction.

## Profile 1 — Local

Use for individual development, offline demos, and deterministic evaluation.

| Concern | Binding |
|---|---|
| Interface | `sac enterprise` CLI |
| Identity | Explicit local actor resolved to `RBACSubject` |
| Persistence | Project-local `.sac/enterprise/` filesystem |
| Workflow | In-process orchestrator with checkpoints and resume |
| Retrieval | Local manifests, lexical/optional semantic retrieval |
| Audit | Local append-only hash chain |
| Network | Denied unless explicitly configured and approved |

Local mode requires Python 3.11+ and repository dependencies. It remains the
default test profile and does not require PostgreSQL, OIDC, or provider keys.

## Profile 2 — Team Server

Use for authenticated multi-user operation.

| Concern | Binding |
|---|---|
| Interface | FastAPI `/v2`, thin CLI client, operator console |
| Identity | OIDC bearer token mapped to tenant-scoped `RBACSubject` |
| Persistence | PostgreSQL 16 + pgvector |
| Workflow | Durable queue, worker lease, heartbeat, fencing, retry, DLQ |
| Integration | GitHub App, Jira, CI callback, governed MCP/tools |
| Audit | PostgreSQL-backed hash chain and redacted evidence export |
| Observability | Trace/timeline APIs and optional OpenTelemetry export |

Required configuration includes the database URL, OIDC issuer/audience, and
separate connector secrets. Credentials must come from environment or an
operator-managed secret store, never the repository.

Every request is authenticated before tenant resolution. Persistence methods
revalidate tenant identity, approval grants are snapshot-bound and single-use,
and live writes fail closed when credentials or grants are absent.

## Profile 3 — On-Premises Team Server

This profile uses the Team Server contract inside an organization-controlled
network and adds operator-owned infrastructure:

- managed PostgreSQL/pgvector with backup, restore, and retention policy;
- organization OIDC and secret management;
- restricted egress and internal GitHub/Jira/MCP endpoints;
- centralized OpenTelemetry collection;
- signed images, deployment policy, and independent security review.

The repository does not claim production readiness for a specific environment.
Operators must supply the external evidence listed in
`security/external-gates.md` before GA promotion.

## Compose Development Profile

`compose.enterprise.yaml` starts the API, PostgreSQL/pgvector, and worker for
development and integration testing. It is not production deployment evidence.

```bash
docker compose -f compose.enterprise.yaml up --build
```

Use the upgrade/rollback and recovery walkthroughs under
`examples/enterprise/demos/v2.5/` when rehearsing schema or artifact changes.

## Verification

```bash
# Local and package contracts
uv run python scripts/verify-package.py
uv run --extra enterprise python -m pytest -q tests/enterprise

# PostgreSQL concurrency and migration lane
./scripts/run-postgres-integration.sh

# Full offline regression
uv run --extra enterprise python -m pytest -q
```

PostgreSQL and live-provider lanes require operator-owned environment
configuration. A skipped lane is not successful production evidence.

## Selection Guide

| Need | Profile |
|---|---|
| Offline learning, local development, deterministic CI | Local |
| Authenticated shared workflows and operator console | Team Server |
| Organization-controlled network and infrastructure | On-Premises Team Server |

Start local. Move to Team Server only when shared identity, durable multi-user
state, or live integrations justify the operational cost.
