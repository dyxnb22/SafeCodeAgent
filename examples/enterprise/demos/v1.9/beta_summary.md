# Enterprise Beta Hardening Demo (v1.9)

## Goal

Demonstrate multi-tenant isolation, compliance evidence export, and performance
budgets on the existing PR review and remediation workflows.

## Steps

```bash
# 1. Run PR review under tenant A
sac enterprise workflow run \
  --task pr_review \
  --input examples/enterprise/fixtures/pr_sql_injection \
  --tenant tenant-a \
  --root .

# 2. Run remediation under tenant B (isolated workspace in eval)
sac enterprise workflow run \
  --task remediation \
  --input examples/enterprise/fixtures/remediation/sql_injection \
  --tenant tenant-b \
  --root .

# 3. Export compliance evidence for a completed run
sac enterprise evidence export --run <run_id> --root .

# 4. Verify eval suites and latency budgets
sac enterprise eval run --suite all --root .
sac enterprise eval dashboard --root .
```

## Expected outcomes

- Retrieval and audit records carry `tenant_id`; cross-tenant retrieval is denied.
- Evidence zip contains manifest, trace, timeline, citations, approvals, audit
  segment, and validation outputs; import verification passes hash-chain check.
- PR review benign fixture completes under the 30s mock-provider budget on CI.
- Eval dashboard flags any case exceeding latency budget thresholds.

## Beta readiness checklist

- Multi-tenant tests: `tests/enterprise/multitenant/`
- Evidence export: `tests/enterprise/evidence/`
- Performance budgets: `tests/enterprise/perf/`
- All eval baselines ratchet green
