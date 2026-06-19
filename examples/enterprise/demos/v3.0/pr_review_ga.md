# GA PR Security Review Demo (v3.0.4)

Repeat v2.2 acceptance against GA contracts (`/v2`, supported OpenAPI, frozen CLI).

## Contract gate

```bash
uv run pytest tests/enterprise/integration/test_pr_review_v2_2.py -q -m "not live_github"
uv run pytest tests/enterprise/contracts/test_public_contract_v3_0.py -q
```

## Offline fixture

- PR fixture: `examples/enterprise/fixtures/pr_sql_injection/pr.json`
- Integration suite: `tests/enterprise/integration/test_pr_review_v2_2.py`

## Expected outcomes

- Webhook ingest queues one governed `pr_review` run.
- Approval gate blocks GitHub write until human decision.
- Traces and evidence remain redacted; GA contract snapshots unchanged.
