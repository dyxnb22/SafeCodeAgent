# GA Vulnerability Remediation Demo (v3.0.4)

Repeat v2.2 remediation acceptance under GA contracts.

## Contract gate

```bash
uv run pytest tests/enterprise/integration/test_remediation_v2_2.py -q -m "not live_github"
uv run pytest tests/enterprise/contracts/test_migration_v2_rc_to_v3_0.py -q
```

## Offline fixture

- Finding: `examples/enterprise/fixtures/remediation/sql_injection/finding.json`
- Integration suite: `tests/enterprise/integration/test_remediation_v2_2.py`

## Expected outcomes

- Patch proposal requires approval before write.
- Checkpoint/rollback preserved; v2.0 RC workflow state contract honored.
