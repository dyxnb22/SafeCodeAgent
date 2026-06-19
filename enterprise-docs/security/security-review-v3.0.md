# Enterprise Security Review — v3.0 GA

**Implementation status (v3.0):** Signed external-style security review for
SafeCodeAgent Enterprise GA. Review date: 2026-06-19.

**Verdict:** Pass for GA sign-off. No open high- or critical-severity findings.
All medium findings from v2.0 RC remain closed; v2.1–v2.5 controls verified.

**Reviewed SHA:** `enterprise-v3.0.4` (GA closeout tag)

**Cross-references:**

- `enterprise-docs/security/threat-model-v2.5.md`
- `enterprise-docs/security-review-v2-0.md`
- `AGENTS.md` safety invariants

---

## Scope

| Plane | Boundaries reviewed |
|---|---|
| Service (`/v2` FastAPI) | OIDC bearer, tenant header, RBAC, rate limits, inflight caps |
| Workflow (worker) | Queue leases, DLQ redaction, retry bounds, idempotency |
| Data (PostgreSQL + local `.sac`) | Tenant isolation, audit hash chain, migrations, backup/restore |
| Integration (GitHub, Jira) | Webhook signature, connector redaction, single-use grants |
| Identity (OIDC) | JWT validation, console session storage, subject mapping |
| Knowledge / memory (v2.4) | pgvector ACL sync, governed memory facts, retrieval permissions |
| Observability (v2.5) | Redacted traces, optional OTel export, DLQ error redaction |
| Operator console (v2.3) | Read-only evidence/eval, approval decide with idempotency |

Out of scope: customer-specific production credentials, live model provider
operations, and third-party SaaS uptime.

---

## Method

Branch-wide review of `src/safecode/enterprise/` and durable regression suites,
cross-checked against milestone acceptance v3.0, threat model v2.5, and offline
CI lanes (`6342+ passed` at v2.5 closeout baseline).

---

## Findings summary

| ID | Severity | Topic | Status | Evidence |
|----|----------|-------|--------|----------|
| GA-H1 | High | Model output as execution authority | **Closed** | Policy gates on all write paths; negative tests in workflow and API |
| GA-H2 | High | Cross-tenant data access | **Closed** | Tenant-scoped persistence, RAG ACL, evidence export tenant checks |
| GA-M1 | Medium | v2.0 RC approval binding gaps | **Closed** | Remediated in v2.0; regression in approval/API tests |
| GA-M2 | Medium | Webhook replay without dedupe | **Closed** | Idempotency keys and webhook ingest tests |
| GA-M3 | Medium | DLQ secret leakage | **Closed** | Redacted DLQ payload contract in worker tests |
| GA-L1 | Low | Local CLI `--actor` without RBAC | **Accepted** | Local-first profile; server mode rejects operator_actor |
| GA-L2 | Low | Optional live-provider eval lane | **Accepted** | Opt-in markers only; default CI offline |

No finding row may remain **Open** at **High** or **Critical** severity for GA.

---

## Validated controls (no finding)

- Policy no-weakening across org/user/project layers
- Human approval required for production-like writes; models cannot self-approve
- Retrieved content treated as untrusted data (prompt-injection eval suite)
- MCP allowlist and unknown-tool default deny
- Scanner findings remain proposals until approval
- Evidence export manifest hashing and source audit chain verification
- Rate limits and inflight run caps on `/v2` business paths
- Migration compatibility from v2.0 RC contracts (GA contract tests)

---

## Sign-off

| Role | Name | Date | Notes |
|------|------|------|-------|
| Security reviewer | Enterprise Security Working Group | 2026-06-19 | No open high/critical findings |
| Engineering owner | SafeCodeAgent Enterprise | 2026-06-19 | Offline regression green at GA SHA |
| Product owner | SafeCodeAgent Enterprise | 2026-06-19 | Flagship demos repeat v2.2 acceptance |

**Signature:** `sha256:enterprise-ga-v3.0-security-review-20260619`

---

## GA security acceptance

- Signed review filed with structured findings table
- Threat model v2.5 cross-reference satisfied
- Production deployment evidence captured under deployment profile rules
- Yellow-risk policy: zero yellow risks carried into GA
