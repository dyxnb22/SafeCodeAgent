# v3.0 Candidate Evidence Export Demo

Verify the frozen evidence-export contract.

```bash
uv run --extra enterprise python -m pytest -q \
  tests/enterprise/evidence \
  tests/enterprise/contracts/test_public_contract_v2_0.py
```

For an existing local run:

```bash
sac enterprise evidence export --run <run_id> --tenant local --root .
```

The bundle must contain an integrity-checked manifest, preserve the audit-chain
contract, and contain no secrets. Offline verification is not external GA
evidence.
