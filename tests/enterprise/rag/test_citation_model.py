"""Tests for Citation model (v1.1.2-T1)."""

import json

from safecode.enterprise.rag.models import Citation
from safecode.enterprise.rag.source_registry import SourceType


def test_citation_json_round_trip():
    citation = Citation(
        citation_id="cite-abc",
        source_id="policy-secure-sql-001",
        source_type=SourceType.security_policy,
        tenant_id="local",
        path="policy.md",
        start_line=1,
        end_line=10,
        score=0.91,
        selection_reason="lex=0.41,sem=0.62",
        permission_verdict="allowed",
        freshness="current",
        hash="sha256:deadbeef",
        text_excerpt="Always parameterize SQL queries.",
    )
    payload = citation.model_dump(mode="json")
    encoded = json.dumps(payload)
    restored = Citation.model_validate(json.loads(encoded))
    assert restored == citation
