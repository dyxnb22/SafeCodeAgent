"""Tests for Markdown loader (v1.1.1-T3)."""

from pathlib import Path

from safecode.enterprise.rag.loaders.loader_markdown import load_markdown_source
from safecode.enterprise.rag.source_registry import KnowledgeSource, SourceType

_SOURCE = KnowledgeSource(
    source_id="policy-test",
    source_type=SourceType.security_policy,
    name="Test policy",
    path_or_uri="policy.md",
    owner="appsec",
    permission_scope=["org"],
    refresh_cadence="static",
    parser="markdown",
)


def test_emits_one_record_per_h1_section(tmp_path: Path):
    (tmp_path / "policy.md").write_text(
        "# Secure SQL\n\nUse parameters.\n\n# Input validation\n\nSanitize input.\n",
        encoding="utf-8",
    )
    result = load_markdown_source(_SOURCE, tmp_path)
    assert len(result.records) == 2
    assert result.records[0].metadata["headings"][0].startswith("h1:")
    assert "Use parameters" in result.records[0].text


def test_preamble_before_first_h1_becomes_separate_record(tmp_path: Path):
    (tmp_path / "policy.md").write_text(
        "Intro guidance before headings.\n\n# Secure SQL\n\nUse parameters.\n",
        encoding="utf-8",
    )
    result = load_markdown_source(_SOURCE, tmp_path)
    assert len(result.records) == 2
    assert "Intro guidance" in result.records[0].text
    assert result.records[0].record_id != result.records[1].record_id


def test_no_h1_emits_single_whole_file_record(tmp_path: Path):
    (tmp_path / "policy.md").write_text("## Only H2\n\nBody text.\n", encoding="utf-8")
    result = load_markdown_source(_SOURCE, tmp_path)
    assert len(result.records) == 1
    assert "Body text" in result.records[0].text


def test_front_matter_lands_in_metadata(tmp_path: Path):
    (tmp_path / "policy.md").write_text(
        "---\ncwe: CWE-89\n---\n# Secure SQL\n\nUse parameters.\n",
        encoding="utf-8",
    )
    result = load_markdown_source(_SOURCE, tmp_path)
    assert result.records[0].metadata["cwe"] == "CWE-89"


def test_record_ids_are_stable_across_runs(tmp_path: Path):
    (tmp_path / "policy.md").write_text("# Secure SQL\n\nUse parameters.\n", encoding="utf-8")
    first = load_markdown_source(_SOURCE, tmp_path).records[0].record_id
    second = load_markdown_source(_SOURCE, tmp_path).records[0].record_id
    assert first == second
