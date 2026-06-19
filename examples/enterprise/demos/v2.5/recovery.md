# v2.5 worker recovery demo

Exercise poison-message DLQ handling and transient retry recovery:

```bash
uv run pytest tests/enterprise/worker/test_dlq_offline.py tests/enterprise/worker/test_lease_recovery.py -q
```

Poison commands land in `dlq.jsonl` with redacted errors; healthy jobs
continue after a poisoned message is drained.
