# SafeCodeAgent Enterprise v2.0.0-rc Release Notes

**Release candidate:** Enterprise security engineering agent platform
**Baseline kernel tag:** `v7.1.5`
**Enterprise stages delivered:** v1.0 through v2.0
**Contract snapshot:** `tests/enterprise/contracts/snapshots/`

---

## Highlights

- **PR security review workflow** — offline fixtures, risk tiers, cited reports, gated PR comments
- **Vulnerability remediation workflow** — finding ingest, patch proposal, checkpoint/rollback, revalidation
- **Governance** — policy precedence, RBAC, approval tiers, hash-chain audit
- **Permission-aware RAG** — hybrid retrieval with tenant and scope filters
- **AgentOps** — redacted traces, timelines, eval dashboard
- **Beta hardening (v1.9)** — multi-tenant isolation, compliance evidence export, latency budgets
- **RC contracts (v2.0)** — frozen public surface snapshot tests for CLI, trace, evidence, eval baselines

---

## Public contract snapshot (v2.0.1)

Frozen contracts (see `tests/enterprise/contracts/test_public_contract_v2_0.py`):

| Contract | Snapshot file |
|----------|----------------|
| `sac enterprise` CLI commands | `enterprise_cli.json` |
| Trace event schema | `trace_event.json` |
| Run timeline schema | `timeline.json` |
| Evidence export manifest | `evidence_export.json` |
| Eval baseline format | `eval_baseline.json` |
| Workflow run state | `workflow_state.json` |

Any intentional contract change must update the matching snapshot in the same PR.

---

## Flagship CLI workflows

```bash
sac enterprise workflow run --task pr_review --input <fixture> --root .
sac enterprise workflow run --task remediation --input <fixture> --root .
sac enterprise evidence export --run <run_id> --tenant <tenant_id> --root .
sac enterprise eval run --suite all --root .
sac enterprise eval dashboard --root .
```

Demos: `examples/enterprise/demos/v1.7/`, `v1.8/`, `v1.9/`, `v2.0/`

---

## Verification

```bash
uv lock --check
python3 scripts/verify-package.py
PYTHONPATH=src python3 -m pytest -q
```

At reviewed RC closeout: **6012 passed, 5 skipped**, Enterprise tests and eval
baseline ratchets green, package verification successful.

---

## Security review

External-style security review notes: `enterprise-docs/security-review-v2-0.md`
Deployment guidance: `enterprise-docs/deployment-profiles.md`

---

## Known RC limitations

- CLI-only surface (no web dashboard)
- Mock-provider default for deterministic eval/workflow lanes
- Contract snapshot covers enterprise surface; kernel contracts remain in `tests/test_public_contract_snapshots.py`
- Post-RC work tracked as v2.1+ in `product-planning/version-roadmap.md`

---

## Upgrade from enterprise beta (v1.9)

- `tenant_id` is now enforced on policy snapshots and audit metadata
- New command: `sac enterprise evidence export --run <id> --tenant <tenant_id>`
- Contract snapshot tests will fail if CLI or schema fields change without snapshot updates
