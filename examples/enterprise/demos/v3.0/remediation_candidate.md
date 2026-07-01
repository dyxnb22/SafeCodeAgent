# v3.0 Candidate Vulnerability Remediation Demo

Verify offline remediation and migration compatibility.

```bash
uv run --extra enterprise python -m pytest -q \
  tests/enterprise/integration/test_remediation_v2_2.py \
  tests/enterprise/contracts/test_migration_v2_rc_to_v3_0.py \
  -m "not live_github"
```

Fixture: `examples/enterprise/fixtures/remediation/sql_injection/finding.json`.

The patch remains a proposal until approval; checkpoint and rollback contracts
must remain intact. Offline verification is not external GA evidence.
