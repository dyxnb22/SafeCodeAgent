# v3.0 GA production deployment evidence

**Profile:** on-prem / production-like (`compose.enterprise.yaml`)  
**Recorded:** 2026-06-19  
**Environment:** loopback-only compose stack; no customer credentials committed

## Stack bring-up

```bash
bash scripts/enterprise-up.sh
curl -sf http://127.0.0.1:8080/healthz
curl -sf http://127.0.0.1:8080/readyz
curl -sf http://127.0.0.1:8080/version
```

Expected `/version` payload fields: `service`, `api_version` (`3.0.0`), `contract_status` (`supported`).

## Observed metrics (representative)

| Signal | Source | Notes |
|--------|--------|-------|
| API liveness | `/healthz` | Returns `{"status":"ok"}` |
| Readiness | `/readyz` | 503 when persistence unavailable |
| Worker queue depth | PostgreSQL `enterprise.worker_queue` | Bounded by inflight caps |
| Rate limit denials | API 429 problem+json | Tenant-scoped RPM |

## Audit chain verification

Offline contract (no live DB required for CI):

```bash
uv run pytest tests/enterprise/persistence/test_backend_contract.py -q
uv run pytest tests/enterprise/deploy/test_production_evidence_offline.py -q
```

## Incident handling rehearsal

1. Stop worker container; confirm `/readyz` remains green while API serves read paths.
2. Replay poison queue message; confirm DLQ row is redacted (`tests/enterprise/worker/`).
3. Run `bash scripts/enterprise-rollback.sh` against tagged release.

## Backup evidence

```bash
bash scripts/enterprise-backup.sh /var/lib/safecode/enterprise ga-backup.tar.gz
bash scripts/enterprise-restore.sh ga-backup.tar.gz /var/lib/safecode/restore
uv run pytest tests/enterprise/persistence/test_backup_restore_offline.py -q
```

## Tear-down

```bash
docker compose -f compose.enterprise.yaml down -v
```

No debug payloads, tokens, or host-specific paths are stored in this document.
