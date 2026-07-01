# v3.0 Candidate Secure Planning Demo

Verify ticket-grounded secure planning and current public contracts.

```bash
uv run --extra enterprise python -m pytest -q \
  tests/enterprise/workflow/test_secure_planning_offline.py \
  tests/enterprise/contracts/test_public_contract_v3_0.py
```

Offline input:

```bash
sac enterprise workflow run \
  --task secure_planning \
  --input examples/enterprise/fixtures/ticket_password_reset/ticket.md \
  --root .
```

Retrieved content remains untrusted, citations preserve permission scope, and
ticket writes remain proposals until approval. This is not external GA evidence.
