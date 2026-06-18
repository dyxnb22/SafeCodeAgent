"""Tests for Chunk model (v1.1.2-T1)."""

import json

from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.source_registry import SourceType


def test_chunk_json_round_trip():
    chunk = Chunk(
        chunk_id="chunk-abc",
        source_id="policy-secure-sql-001",
        tenant_id="local",
        path="policy.md",
        start_line=1,
        end_line=10,
        source_type=SourceType.security_policy,
        permission_scope=["org", "appsec"],
        freshness="current",
        text="Always parameterize SQL queries.",
        hash="sha256:deadbeef",
        metadata={"headings": ["h1:Secure SQL"]},
    )
    payload = chunk.model_dump(mode="json")
    encoded = json.dumps(payload)
    restored = Chunk.model_validate(json.loads(encoded))
    assert restored == chunk
