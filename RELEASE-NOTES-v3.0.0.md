# SafeCodeAgent Enterprise v3.0.0 GA Release Notes

**General availability:** Enterprise security engineering agent platform  
**Baseline kernel tag:** `v7.1.5`  
**Enterprise stages delivered:** v1.0 through v3.0 GA  
**GA contract snapshot:** `tests/enterprise/contracts/snapshots/ga_v3_0.json`

---

## Highlights

- **GA contract freeze** — `/v2` Team Server, Operator Console, and v2.0 RC CLI/trace/evidence contracts marked `supported`
- **Migration path** — v2.0 RC → v3.0 GA compatibility tests for settings, OpenAPI, CLI, and persistence
- **Signed security review** — `enterprise-docs/security/security-review-v3.0.md` with no open high/critical findings
- **Production evidence** — on-prem compose profile with health probes, audit chain, backup/restore, and DLQ rehearsal
- **Flagship demos** — PR review, remediation, secure planning, evidence export, console approval under GA contracts

---

## Contract changes since v2.0 RC

| Surface | v2.0 RC | v3.0 GA |
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
| PR review | v2.2 integration + GA contract |
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

At GA closeout: full offline regression green; eval baselines locked in `tests/enterprise/eval/baselines/ga_lock_v3_0.json`.

---

## Security

- GA review: `enterprise-docs/security/security-review-v3.0.md`
- Threat model: `enterprise-docs/security/threat-model-v2.5.md`
- Deployment profiles: `enterprise-docs/deployment-profiles.md`

---

## Known GA limitations

- Live GitHub/Jira/OIDC lanes remain opt-in; default CI is offline
- Console requires separate build (`console/`); API remains the contract boundary
- pgvector profile is optional; lexical RAG remains the offline default

---

## Tags

- Milestone tags: `enterprise-v3.0.1` … `enterprise-v3.0.4`
- GA tag: `enterprise-v3.0.0` (closeout)
