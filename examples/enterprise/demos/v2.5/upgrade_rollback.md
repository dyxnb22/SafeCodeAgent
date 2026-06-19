# v2.5 upgrade and rollback demo

Bring up the on-prem stack, then rehearse rollback:

```bash
bash scripts/enterprise-up.sh
# optional tagged rollback:
ENTERPRISE_ROLLBACK_TAG=v2.5.1 bash scripts/enterprise-rollback.sh
```

Validate the compose contract offline:

```bash
uv run pytest tests/enterprise/deploy/test_compose_contract_offline.py -q
```

Backup before upgrade:

```bash
bash scripts/enterprise-backup.sh /var/lib/safecode/enterprise backup.tar.gz
bash scripts/enterprise-restore.sh backup.tar.gz /var/lib/safecode/restore
```
