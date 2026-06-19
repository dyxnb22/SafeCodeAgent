# Enterprise RC Dashboard (v2.0)

## Goal

Publish release-candidate readiness: eval pass rate, safety invariants, and
contract snapshot status for interview and gate review.

## Generate dashboard

```bash
# Run all enterprise eval suites (mock provider, deterministic)
sac enterprise eval run --suite all --root .

# View Markdown dashboard
sac enterprise eval dashboard --root .
# Artifact: .sac/enterprise/eval/latest.md

# Contract snapshot gate
PYTHONPATH=src python3 -m pytest -q tests/enterprise/contracts

# Package verification
python3 scripts/verify-package.py
```

## RC acceptance checklist

| Gate | Command / artifact | Expected |
|------|-------------------|----------|
| Eval suites | `eval run --suite all` | All cases pass; baselines ratchet green |
| Safety invariants | eval case `safety_assertions` | `audit_chain_intact`, `no_unauthorized_mutation` |
| Contracts | `tests/enterprise/contracts/` | Snapshot match |
| Flagship workflows | demos v1.7, v1.8, v1.9 | Runnable on clean clone |
| Security review | `enterprise-docs/security-review-v2-0.md` | No open high severity |
| Release notes | `RELEASE-NOTES-v2.0.0-rc.md` | Links contract snapshot |

## Trace dashboard (per run)

```bash
sac enterprise workflow run --task pr_review \
  --input examples/enterprise/fixtures/pr_sql_injection --root .
sac enterprise trace show <run_id> --root .
```

Timeline includes `safety_invariants` block: audit chain, redaction, grant consume.

## Interview anchor

- Kernel tag `v7.1.5` + Enterprise stages v1.0–v1.9
- RC adds frozen public contracts and deployment profiles
- Evidence export + tenant isolation demonstrate enterprise beta hardening
