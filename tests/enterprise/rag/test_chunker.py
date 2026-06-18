"""Tests for enterprise chunker (v1.1.2-T2)."""

from pathlib import Path

from safecode.enterprise.rag.chunker import chunk_records
from safecode.enterprise.rag.loaders.loader_code import load_code_source
from safecode.enterprise.rag.loaders.loader_markdown import load_markdown_source
from safecode.enterprise.rag.source_registry import KnowledgeSource, SourceType

_POLICY = KnowledgeSource(
    source_id="policy-test",
    source_type=SourceType.security_policy,
    name="Policy",
    path_or_uri="policy.md",
    owner="appsec",
    permission_scope=["org"],
    refresh_cadence="static",
    parser="markdown",
)

_CODE = KnowledgeSource(
    source_id="code-app",
    source_type=SourceType.code,
    name="Code",
    path_or_uri="app.py",
    owner="dev",
    permission_scope=["org"],
    refresh_cadence="on_demand",
    parser="code",
)


def test_markdown_records_produce_chunks(tmp_path: Path):
    (tmp_path / "policy.md").write_text(
        "# Secure SQL\n\n## Parameterized queries\n\nUse bind params.\n",
        encoding="utf-8",
    )
    records = load_markdown_source(_POLICY, tmp_path).records
    chunks = chunk_records(records, _POLICY)
    assert chunks
    assert all(chunk.source_type == SourceType.security_policy for chunk in chunks)


def test_python_records_produce_chunks(tmp_path: Path):
    (tmp_path / "app.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    records = load_code_source(_CODE, tmp_path).records
    chunks = chunk_records(records, _CODE)
    assert len(chunks) == 1
    assert chunks[0].metadata["symbol_name"] == "helper"
