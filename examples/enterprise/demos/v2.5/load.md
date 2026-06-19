# v2.5 load profile demo

Run the offline load profile ratchet:

```bash
uv run pytest tests/enterprise/perf/test_load_profile_offline.py -q
```

The documented `LOAD_PROFILE_MS` envelope stays under
`WORKFLOW_LATENCY_BUDGET_MS` and default `CostBudget` limits.
