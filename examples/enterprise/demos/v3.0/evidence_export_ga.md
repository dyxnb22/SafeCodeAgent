# GA Evidence Export Demo (v3.0.4)

Export compliance evidence under the frozen v2.0 RC evidence contract.

## Contract gate

```bash
uv run pytest tests/enterprise/evidence/ -q
uv run pytest tests/enterprise/contracts/test_public_contract_v2_0.py -q
```

## Offline command

```bash
sac enterprise evidence export --run <run_id> --tenant local --root .
```

## Expected outcomes

- Manifest includes `source_audit_chain_verified`.
- Bundle file names match `evidence_export.json` snapshot.
- No secrets in exported artifacts.
