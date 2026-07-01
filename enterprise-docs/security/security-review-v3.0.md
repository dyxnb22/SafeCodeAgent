# Enterprise Security Review - v3.0 Candidate

**Status:** Internal remediation review complete; independent external sign-off pending.

**Verdict:** Not approved for GA. Code findings are remediated in the current
candidate, but independent review, production deployment, and stable
live-provider evidence gates remain open.

**Reviewed baseline:** `08bc68f35461cf26a3cdc35965bf7c656ca6d65d`

## Scope

The review covers the `/v2` API, worker, local and PostgreSQL persistence,
GitHub/Jira connectors, RAG and memory, console, deployment tooling, tracing,
and release evidence. It is cross-checked against
`enterprise-docs/security/threat-model-v2.5.md`, `AGENTS.md`, current
contracts, and durable security tests.

## Findings Summary

| ID | Severity | Topic | Status | Remediation evidence |
|---|---|---|---|---|
| GA-H1 | High | Memory admission bypassed approval binding | Closed internally | Bound grant, digest, expiry, policy snapshot, and negative tests |
| GA-H2 | High | Tenant identifiers allowed path escape | Closed internally | Canonical validator at identity and persistence boundaries |
| GA-H3 | High | Run command endpoints omitted RBAC | Closed internally | Developer minimum role on start, resume, and cancel |
| GA-H4 | High | Caller-controlled rate-limit bucket | Closed internally | Limiting after authenticated tenant resolution |
| GA-H5 | High | Compose could not apply pgvector migration | Closed internally | `pgvector/pgvector:pg16` is mandatory |
| GA-M1 | Medium | Boolean approval produced false live-write success | Closed internally | Live writes require a bound grant or return BLOCK |
| GA-M2 | Medium | Development private key committed | Closed internally | Ephemeral gitignored key generation; committed key removed |
| GA-M3 | Medium | Restore accepted unsafe tar members | Closed internally | Validated extraction rejects traversal, links, and devices |
| GA-G1 | Gate | Independent security reviewer signature | **Open** | Reviewer must sign the final candidate SHA |
| GA-G2 | Gate | Production deployment evidence | **Open** | Operator-owned artifact required |
| GA-G3 | Gate | Stable live-provider evaluation run | **Open** | Provider-owned eval artifact required |

The open gate rows are release blockers. An agent cannot waive them.

## Validated Controls

- Model output is not execution authority.
- GitHub/Jira live writes consume target- and policy-bound grants.
- Tenant IDs are validated before identity mapping, persistence, or path use.
- API write commands require authenticated tenant scope and RBAC.
- Memory admission requires expiry, provenance, redaction, and a single-use grant.
- Default tests remain offline; live lanes are separately evidenced.

## Independent Sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| Security reviewer | Pending independent reviewer | - | PENDING |
| Engineering owner | SafeCodeAgent Enterprise | 2026-06-19 | Internal remediation only |
| Product owner | Pending GA gate completion | - | PENDING |

An agent, model, code author, or repository test cannot fill the independent
reviewer row. Sign-off must record the immutable candidate SHA and detached
signature supplied by the designated reviewer.

## GA Security Acceptance

- Internal code findings: complete after final regression verification.
- Independent signed review: pending.
- Production deployment evidence: pending external artifact.
- Stable live-provider run: pending external artifact.
- GA status: blocked until all three gates are independently verified.
