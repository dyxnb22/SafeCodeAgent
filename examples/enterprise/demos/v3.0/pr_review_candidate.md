# v3.0 Candidate PR Security Review Demo

Verify the offline PR review and frozen `/v2` contracts.

```bash
uv run --extra enterprise python -m pytest -q \
  tests/enterprise/integration/test_pr_review_v2_2.py \
  tests/enterprise/contracts/test_public_contract_v3_0.py \
  -m "not live_github"
```

Fixture: `examples/enterprise/fixtures/pr_sql_injection/pr.json`.

Expected behavior:

- Webhook ingest queues one tenant-scoped review run.
- A human approval gate blocks GitHub mutation.
- Trace and evidence output remains redacted.

This demo does not claim a live GitHub run or Enterprise GA approval.
