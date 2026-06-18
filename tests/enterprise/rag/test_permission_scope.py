"""Tests for permission scope assignment (v1.1.2-T3)."""

from safecode.enterprise.rag.models import Chunk
from safecode.enterprise.rag.permission_scope import (
    actor_can_access_chunk,
    assign_permission_scope,
    drop_unscoped_chunks,
)
from safecode.enterprise.rag.source_registry import SourceType


def _chunk(scope: list[str]) -> Chunk:
    return Chunk(
        chunk_id="chunk-1",
        source_id="policy-secure-sql-001",
        path="policy.md",
        start_line=1,
        end_line=2,
        source_type=SourceType.security_policy,
        permission_scope=scope,
        freshness="current",
        text="Use parameterized queries.",
        hash="sha256:abc",
    )


def test_assign_permission_scope_copies_parent_scope():
    assigned = assign_permission_scope([_chunk([])], ["org", "appsec"])
    assert assigned[0].permission_scope == ["org", "appsec"]


def test_drop_unscoped_chunks_emits_event():
    result = drop_unscoped_chunks([_chunk([])])
    assert result.chunks == []
    assert result.events[0]["type"] == "chunk.unscoped"


def test_actor_access_fail_closed_on_tenant_mismatch():
    chunk = _chunk(["org"]).model_copy(update={"tenant_id": "tenant-a"})
    assert not actor_can_access_chunk(chunk, ["org"], actor_tenant="tenant-b")


def test_actor_access_requires_scope_subset():
    chunk = _chunk(["org", "appsec"])
    assert actor_can_access_chunk(chunk, ["org", "appsec", "secops"])
    assert not actor_can_access_chunk(chunk, ["org"])
