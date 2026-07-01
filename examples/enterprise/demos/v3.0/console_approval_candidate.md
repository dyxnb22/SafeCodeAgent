# v3.0 Candidate Console Approval Demo

Verify console-driven approval against the supported `/v2` API contract.

```bash
uv run --extra enterprise python -m pytest -q \
  tests/enterprise/console/test_approval_flow_offline.py \
  tests/enterprise/contracts/test_public_contract_v2_3.py
```

Expected behavior:

- `GET /v2/approvals` is tenant scoped.
- `POST /v2/approvals/{approval_id}/decide` requires authentication and an
  `Idempotency-Key`.
- Replays do not create duplicate grants or bypass authorization.

This offline demo verifies contracts; it is not external GA evidence.
