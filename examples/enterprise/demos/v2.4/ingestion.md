# v2.4 Knowledge Ingestion Demo

Demonstrates incremental ingest against the persistent pgvector index.

## Offline verification

```bash
uv run pytest tests/enterprise/rag/test_incremental_ingest_offline.py -q -m "not postgres_integration"
uv run pytest tests/enterprise/rag/test_vector_store_offline.py -q
```

## Notes

- Re-ingest on unchanged input is a deterministic no-op.
- Tenant boundaries are enforced at retrieval and in SQL filters.
