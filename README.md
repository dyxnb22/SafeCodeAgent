# SafeCodeAgent Enterprise

**Enterprise secure-change agent platform** — a governed enterprise security engineering agent platform for PR review, vulnerability remediation, secure
planning, evidence export, and approval-gated workflows.

SafeCodeAgent Enterprise extends the completed SafeCodeAgent safety kernel
(policy-gated writes, checkpoint/rollback, hash-chain audit, sandbox gates)
into a workflow-first platform with permission-aware RAG, RBAC, human approval,
typed connectors/MCP, trace observability, and deterministic evaluation.

> **Current status:** `v3.0` **candidate** — portfolio track complete for
> presentation; **enterprise GA external gates pending** (independent security
> review, production-like deployment evidence, stable live-provider run).
> Portfolio final ≠ enterprise GA. Live state:
> [`.agents/context/progress.json`](.agents/context/progress.json).

---

## What It Does

- **PR security review** — ingest PR evidence, retrieve policy/code citations,
  analyze risk, propose reports, gate high-risk writes behind human approval.
- **Vulnerability remediation** — ingest scanner findings, plan patches, validate
  proposals, and refuse execution without grants.
- **Secure implementation planning** — ticket/issue grounding with governed
  tool proposals.
- **Evidence export** — standalone `sac enterprise evidence export --run <id>`
  for completed runs (compliance bundle with timeline, checkpoint, and audit
  chain verification). The `compliance_export` workflow task is not yet
  implemented.
- **Approval workflow** — scoped, single-use grants bound to proposal snapshots;
  models never self-approve.

Critical invariant: **model output is never execution authority.** Writes and
commands stay policy-gated, auditable, and recoverable via checkpoint and
rollback.

---

## 30-Second Quickstart

From a clean checkout (offline, no provider keys required):

```bash
uv sync
PYTHONPATH=src python3 -m pytest tests/enterprise/cli/test_demo_command.py -q
uv run sac demo --list
uv run sac demo pr-review --offline
```

The demo uses `examples/enterprise/fixtures/pr_sql_injection/`. By default it
runs in a disposable temporary workspace and does **not** write persistent state
under the repository root `.sac`. Use
`uv run sac demo pr-review --offline --output-dir <path>` only when you
intentionally want to keep run artifacts.

---

## Demo

Offline PR review transcript (deterministic, redacted snapshot):

- [examples/enterprise/demos/v3.2/transcripts/pr-review.txt](examples/enterprise/demos/v3.2/transcripts/pr-review.txt)

Run live:

```bash
uv run sac demo pr-review --offline
```

Case study walkthrough:
[product-planning/case-study-secure-change-platform.md](product-planning/case-study-secure-change-platform.md)

---

## Architecture

High-level poster (implemented planes, honest GA status):

- [docs/architecture-poster.md](docs/architecture-poster.md)

Normative post-RC architecture:

- [enterprise-docs/platform-architecture-v2.md](enterprise-docs/platform-architecture-v2.md)

Implemented v1 architecture overview:

- [enterprise-docs/system-architecture-v1.md](enterprise-docs/system-architecture-v1.md)

---

## Security and Governance

External GA gates (cannot be closed by repository-local agents):

- [enterprise-docs/security/external-gates.md](enterprise-docs/security/external-gates.md)

`v3.0` candidate security review (not external sign-off):

- [enterprise-docs/security/security-review-v3.0.md](enterprise-docs/security/security-review-v3.0.md)

Governance design:

- [enterprise-docs/security-governance-plan.md](enterprise-docs/security-governance-plan.md)

Release notes (candidate, not GA approved):

- [RELEASE-NOTES-v3.0.0.md](RELEASE-NOTES-v3.0.0.md)

---

## Interview Materials

- [product-planning/case-study-secure-change-platform.md](product-planning/case-study-secure-change-platform.md) — 15-minute secure-change walkthrough with code/test citations
- [product-planning/interview-master-narrative.md](product-planning/interview-master-narrative.md) — talking points and demo flows

---

## Tests

Reproduce verification locally. Use command exit status and captured CI
artifacts for the exact commit as evidence; suite growth and optional-dependency
skips make counts copied into prose stale:

```bash
PYTHONPATH=src python3 -m pytest tests/enterprise -q
PYTHONPATH=src python3 -m pytest tests/enterprise/cli/test_demo_command.py -q
PYTHONPATH=src python3 -m pytest tests/enterprise/test_no_false_ga_claims.py -q
```

Optional full regression (longer):

```bash
PYTHONPATH=src python3 -m pytest -q
```

Portfolio docs/link hygiene tests live under `tests/enterprise/` (false-GA
claims, README links, documentation path references).

---

## Links Map

| Topic | Entry |
|-------|-------|
| Portfolio roadmap | [product-planning/post-ga-portfolio-roadmap.md](product-planning/post-ga-portfolio-roadmap.md) |
| PR-sized tasks | [product-planning/execution-backlog.md](product-planning/execution-backlog.md) |
| Planning index | [product-planning/README.md](product-planning/README.md) |
| Technical docs | [enterprise-docs/README.md](enterprise-docs/README.md) |
| Platform architecture v2 | [enterprise-docs/platform-architecture-v2.md](enterprise-docs/platform-architecture-v2.md) |
| Progress state | [.agents/context/progress.json](.agents/context/progress.json) |

### Foundation / Background Docs

These predate the executable enterprise delivery track but remain useful context:

- [product-planning/roadmap.md](product-planning/roadmap.md) — phase narrative (foundation)
- [product-planning/implementation-backlog.md](product-planning/implementation-backlog.md) — coarse themes (foundation)
- [enterprise-docs/architecture.md](enterprise-docs/architecture.md) — early architecture notes (foundation)
- [enterprise-docs/legacy-assets.md](enterprise-docs/legacy-assets.md) — reusable kernel mapping (foundation)

Legacy SafeCodeAgent product docs live on `main` and `archive/safecodeagent-final`.

---

## Development

```bash
uv sync
uv run sac --help
uv run sac enterprise --help
```

Repository rules for agents: [AGENTS.md](AGENTS.md).
