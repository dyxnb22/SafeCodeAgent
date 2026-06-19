# Enterprise Deployment Profiles

**Implementation status (v2.0):** Planning document for RC; profiles describe
supported deployment shapes. Implementation of hosted variants may follow v2.0.

This document describes three deployment profiles for SafeCodeAgent Enterprise.
Each profile lists components, security posture, dependencies, and known
limitations. Executable behavior is defined by code and tests; this file is
guidance for operators.

---

## Profile 1 — Local Single-User

### Components

- `sac enterprise` Typer CLI on a developer workstation
- `.sac/` runtime state under the project root (runs, traces, approvals, audit)
- Local knowledge manifest (`examples/enterprise/knowledge_sources.yaml`)
- Optional mock LLM provider (default eval/workflow lane)

### Security posture

- Policy, RBAC, and approval gates enforced locally
- No network I/O in default offline workflow and connector modes
- Strict trace and evidence redaction profiles by default
- Audit hash chain at `.sac/logs/events.jsonl`
- `tenant_id` defaults to `local`; single-tenant operation

### Dependencies

- Python 3.11+
- Repository install (`uv sync` / editable install)
- No database, no external object store

### Known limitations

- No multi-user concurrency controls on `.sac/` (single operator assumed)
- No centralized policy distribution
- Live provider and GitHub modes require explicit configuration and approval

---

## Profile 2 — Team Server

### Components

- Shared filesystem or volume mount for `.sac/` per project workspace
- Same CLI entrypoint; operators SSH or use a shared build agent
- Tenant-tagged retrieval records and audit filtering via `tenant_id` (v1.9.1+)
- Eval baselines and dashboards under `.sac/enterprise/eval/`

### Security posture

- Tenant isolation enforced in RAG retrieval, audit reads, and evidence export
- Approval inbox shared; human approvers must use distinct actor IDs
- Evidence export produces redacted zip bundles per run
- Org/user/project policy precedence unchanged from local profile

### Dependencies

- Python 3.11+ on server
- Shared POSIX filesystem with appropriate UNIX permissions
- Optional CI runner for eval ratchet (`PYTHONPATH=src pytest`)

### Known limitations

- No built-in web UI or SSO (CLI only through v2.0)
- No built-in authentication or SSO; filesystem identity remains the operator boundary
- Shared multi-process approval stores do not yet provide locking
- No horizontal scaling of workflow orchestrator

### PostgreSQL integration lane (v2.1.3+)

Use this disposable profile for migration, `SERIALIZABLE`, and audit parity
acceptance. It is **not** the full v2.1.7 Team Server Compose stack.

```bash
./scripts/run-postgres-integration.sh
```

Or set `SAC_ENTERPRISE_TEST_DATABASE_URL` to any supported PostgreSQL 16+
instance and run:

```bash
uv run pytest tests/enterprise/persistence/postgres -m postgres_integration -q
```

Default Compose DSN:
`postgresql://safecode:safecode_test@127.0.0.1:5432/safecode_enterprise_test`

Compose file: `compose/postgres-integration.yaml` (loopback-bound, tmpfs data).

---

## Profile 3 — On-Prem Hybrid

### Components

- Enterprise CLI and workflows on-premises
- Optional live LLM providers (Anthropic/OpenAI) via configured endpoints
- Optional GitHub connector for PR read/write (gated, offline by default)
- MCP servers from local allowlist (`examples/enterprise/mcp_allowlist.yaml`)
- Compliance evidence export to air-gapped review workstations

### Security posture

- Network egress denied unless explicitly allowed by policy and sandbox
- MCP and connector writes require classification + approval tiers
- Evidence export excludes debug artifacts unless `allow_debug_traces` policy bit
- Scanner invocation through sandbox proposal pipeline

### Dependencies

- Python 3.11+
- Corporate proxy/CA trust store if providers use TLS inspection
- Semgrep/pip-audit on PATH for scanner nodes (optional)
- GitHub token in user-level config (never committed)

### Known limitations

- Hybrid profile does not include hosted multi-region HA
- Provider latency and availability are customer-operated concerns
- OpenTelemetry export reserved post-v2.0

---

## Profile Selection Guide

| Requirement | Recommended profile |
|---------------|---------------------|
| Individual developer, offline demo | Local single-user |
| Small AppSec team, shared repo | Team server |
| Regulated environment, approved providers | On-prem hybrid |

---

## RC Verification Commands

```bash
# Package and regression
python3 scripts/verify-package.py
PYTHONPATH=src python3 -m pytest -q tests/enterprise/contracts

# Flagship workflows (local profile)
sac enterprise workflow run --task pr_review --input examples/enterprise/fixtures/pr_sql_injection --root .
sac enterprise workflow run --task remediation --input examples/enterprise/fixtures/remediation/sql_injection --root .
sac enterprise evidence export --run <run_id> --tenant local --root .
sac enterprise eval run --suite all --root .
```
