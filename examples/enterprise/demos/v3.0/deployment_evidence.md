# v3.0 Candidate Deployment Verification Runbook

**Status:** Pending operator-owned production-like execution evidence.

This file is a maintained runbook, not proof that a deployment occurred. Raw
logs and credentials belong in access-controlled CI artifacts. The GA reviewer
must link an immutable artifact to the final candidate SHA.

## Required Stack Verification

```bash
bash scripts/enterprise-up.sh
curl -sf http://127.0.0.1:8080/healthz
curl -sf http://127.0.0.1:8080/readyz
curl -sf http://127.0.0.1:8080/version
```

Record candidate SHA, image digests, migration versions, probe output,
PostgreSQL/pgvector version, worker recovery, redacted DLQ behavior, rate limits,
and audit chain verification.

## Required Recovery Verification

1. Back up PostgreSQL and the Enterprise artifact volume with the approved
   environment-specific procedure.
2. Restore into an isolated target and verify the audit chain.
3. Set `ENTERPRISE_ROLLBACK_ROOT` to an immutable previous release checkout and
   run `scripts/enterprise-rollback.sh`.
4. Attach redacted command output to the operator-owned evidence artifact.

## Offline Preconditions

```bash
uv run --extra team-server pytest tests/enterprise/deploy/test_production_evidence_offline.py -q
uv run --extra team-server pytest tests/enterprise/persistence/test_backup_restore_offline.py -q
```

Passing offline checks proves the runbook contract only. It does not satisfy
the deployment gate without the external execution artifact.
