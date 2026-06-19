# SafeCodeAgent Enterprise v3.0.0 Candidate Release Notes

> GA promotion is pending independent security sign-off, production deployment
> evidence, and one stable live-provider evaluation run. The existing
> `enterprise-v3.0.0` tag identifies the pre-remediation candidate and must not
> be represented as an approved GA build.

**Release status:** Candidate; not approved for general availability
**Baseline kernel tag:** `v7.1.5`  
**Enterprise stages delivered:** v1.0 through v2.5; v3.0 gates pending
**Candidate contract snapshot:** `tests/enterprise/contracts/snapshots/ga_v3_0.json`

---

## Highlights

- **Candidate contract freeze** — `/v2`, console, and v2.0 RC contracts are snapshot-tested
- **Migration path** — v2.0 RC compatibility tests cover settings, OpenAPI, CLI, and persistence
- **Internal security remediation** — code findings are closed; independent sign-off remains pending
- **Deployment runbook** — operator-owned production execution evidence remains pending
- **Flagship demos** — offline PR review, remediation, planning, evidence, and approval flows

---

## Contract changes since v2.0 RC

| Surface | v2.0 RC | v3.0 candidate |
|---------|---------|---------|
| Enterprise CLI / trace / evidence / eval | `supported` (frozen) | `supported` (unchanged snapshots) |
| Team Server OpenAPI | not published | `supported` at `/v2` |
| Operator Console | not published | `supported` read/write boundary |
| API version metadata | n/a | `3.0.0` (paths remain `/v2` per D29) |

Breaking changes require a decision log entry and snapshot update in the same change.

---

## Migration from v2.0 RC

1. Continue using local-first CLI workflows; no URL rewrite required (`/v2` prefix unchanged).
2. Run migration compatibility tests:

```bash
uv run pytest tests/enterprise/contracts/test_migration_v2_rc_to_v3_0.py -q
```

3. For Team Server profile, configure `SAC_ENTERPRISE_*` settings; v2.0-era local mode (`operator_actor`) remains valid.
4. Apply PostgreSQL migrations in order when upgrading server deployments (`src/safecode/enterprise/persistence/postgres/migrations/`).

---

## Flagship demos

Location: `examples/enterprise/demos/v3.0/`

| Demo | Acceptance reference |
|------|---------------------|
| PR review | v2.2 integration + candidate contract |
| Remediation | v2.2 integration + v2.0 state contract |
| Secure planning | v2.4 workflow |
| Evidence export | v2.0 evidence contract |
| Console approval | v2.3 console contract |

---

## Verification

```bash
uv lock --check
python3 scripts/verify-package.py
PYTHONPATH=src python3 -m pytest -q -m "not postgres_integration"
```

GA promotion additionally requires the three external gates listed at the top
of this document.

---

## Security

- Candidate review: `enterprise-docs/security/security-review-v3.0.md`
- Threat model: `enterprise-docs/security/threat-model-v2.5.md`
- Deployment profiles: `enterprise-docs/deployment-profiles.md`

---

## Candidate Limitations

- Live GitHub/Jira/OIDC lanes remain opt-in; default CI is offline
- Console requires separate build (`console/`); API remains the contract boundary
- pgvector is mandatory for Team Server migrations; lexical RAG remains the offline test default

---

## Tags

- Milestone tags: `enterprise-v3.0.1` … `enterprise-v3.0.4`
- Pre-remediation candidate tag: `enterprise-v3.0.0`
