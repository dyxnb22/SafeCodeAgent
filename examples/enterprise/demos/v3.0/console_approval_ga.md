# GA Console Approval Demo (v3.0.4)

Console-driven approval against supported `/v2` API contracts.

## Contract gate

```bash
uv run pytest tests/enterprise/console/test_approval_flow_offline.py -q
uv run pytest tests/enterprise/contracts/test_public_contract_v2_3.py -q
```

## Offline API replay

- Read path: `GET /v2/approvals?tenant_id=local`
- Write path: `POST /v2/approvals/{approval_id}/decide` with `Idempotency-Key`

## Expected outcomes

- Approval decide requires bearer auth and tenant header.
- Idempotency contract enforced; no duplicate grants.
