"""Chunk id stability tests (v1.1.2-T2)."""

from pathlib import Path

from safecode.enterprise.rag.chunker import chunk_records
from safecode.enterprise.rag.loaders.loader_markdown import load_markdown_source
from safecode.enterprise.rag.source_registry import KnowledgeSource, SourceType

_SOURCE = KnowledgeSource(
    source_id="policy-test",
    source_type=SourceType.security_policy,
    name="Policy",
    path_or_uri="policy.md",
    owner="appsec",
    permission_scope=["org"],
    refresh_cadence="static",
    parser="markdown",
)


def test_same_input_produces_identical_chunk_ids(tmp_path: Path):
    (tmp_path / "policy.md").write_text("# Secure SQL\n\nUse parameters.\n", encoding="utf-8")
    records = load_markdown_source(_SOURCE, tmp_path).records
    first = [chunk.chunk_id for chunk in chunk_records(records, _SOURCE)]
    second = [chunk.chunk_id for chunk in chunk_records(records, _SOURCE)]
    assert first == second
