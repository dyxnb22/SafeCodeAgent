# Enterprise Security Review — v2.0 RC

**Implementation status (v2.0):** External-style security review for Enterprise
Release Candidate. Review date: 2026-06-19.

**Verdict:** Pass for local-first RC. No open high- or medium-severity
findings. M1-M3 were remediated during v2.0 closeout.

---

## Scope

- `src/safecode/enterprise/` (workflow, RAG, governance, connectors, eval, evidence)
- `src/safecode/cli_enterprise.py`
- Approval, audit, tenant isolation, evidence export trust boundaries
- Kernel reuse (`safecode.policy`, `safecode.audit`, `safecode.checkpoint`)

Out of scope: live provider operations, hosted multi-tenant service hardening.

---

## Method

Branch-wide review with focus on enterprise modules, cross-checked against
`AGENTS.md` safety invariants, milestone acceptance, and automated regression
(`6012 passed, 5 skipped` at reviewed RC closeout).

---

## Findings summary

| ID | Severity | Topic | RC status |
|----|----------|-------|-----------|
| M1 | Medium | Approval tamper detection bypass on `list_requests` enforcement paths | **Closed** — tampered records fail closed on list and direct-load paths |
| M2 | Medium | Coarse approval binding (action / policy snapshot / grant) | **Closed** — exact request, tenant, action, policy, proposal digest, and single-use grant are enforced |
| M3 | Medium | Approval audit/trace hardcoded `tenant_id=local` | **Closed** — workflow tenant and policy snapshot propagate through approval and GitHub trace events |
| L1 | Low | CLI `--actor` without RBAC gate | Accepted — local single-user CLI |
| L2 | Low | Grant model not wired to execute path | **Closed with M2** |
| L3 | Low | `resolve_subject` result not applied in workflow run | Accepted — local dev default |
| L4 | Low | Manifest path containment at load time | Accepted — project-controlled manifest |

---

## Validated controls (no finding)

- Policy no-weakening across org/user/project layers
- Model actors cannot approve their own requests
- RAG tenant isolation (`actor_can_access_chunk` fail-closed)
- MCP allowlist and unknown-tool denial
- Scanner proposal pipeline (no auto-execute without approval)
- Fixture path containment (`resolve_fixture_path`, `resolve_finding_fixture`)
- Evidence export manifest hashing, anchored source-chain verification, and bundled event hashes
- Audit hash chain integrity on primary read path

---

## M1 remediation (v2.0)

`list_requests()` now verifies `request_hash` and raises on tampering, matching
`load_request()` integrity. Enforcement and evidence-export paths cannot silently
omit a corrupted approval record.

---

## M2 remediation

Resume validates the exact `approval-{run_id}` request against tenant, action,
policy snapshot, proposal identity, and proposal SHA-256. Approval creates a
matching grant; `finalize` consumes it immediately before the governed action.
Changed proposals, mismatched policy or tenant, and repeated consumption fail
closed.

---

## M3 remediation

Approval requests and grants carry `tenant_id`; request, decision, consumption,
and GitHub write traces use the workflow tenant and policy snapshot. Evidence
export requires an expected tenant and rejects cross-tenant run access.

---

## RC security acceptance

- No open high-severity findings
- M1 closed in v2.0 delivery
- M1-M3 closed with negative regression coverage
- Deployment posture documented in `enterprise-docs/deployment-profiles.md`
- Public contracts frozen under `tests/enterprise/contracts/`

---

## Post-RC recommendations (v2.1+)

1. RBAC-gate enterprise CLI mutating commands for team-server profile
2. Resolve authenticated subjects instead of trusting local `--actor` values
3. Add multi-process locking for shared approval stores before hosted use
4. Add path containment validation at knowledge manifest load time
