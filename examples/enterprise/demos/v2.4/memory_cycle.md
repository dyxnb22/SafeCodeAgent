# v2.4 Governed Memory Demo

Covers admit, revoke, expire, and audit for long-term memory facts.

## Offline verification

```bash
uv run pytest tests/enterprise/memory/test_memory_governance_offline.py -q
```

## Cycle

1. Admit an approved fact with provenance and approver.
2. Retrieve it as a permission-scoped chunk in hybrid retrieval.
3. Revoke or expire the fact and confirm it no longer surfaces.
4. Verify audit events for each transition.
