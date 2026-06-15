"""Context budget manager tests for v2.0.1."""

from __future__ import annotations

from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.context.budget import ContextBudget, ContextBudgetPacker, estimate_tokens_from_bytes
from safecode.context.collector import ContextCollector
from safecode.context.selector import ContextSelector, SelectedContextSource


def test_budget_packer_reports_sources_and_truncation() -> None:
    # B17 fix: when aggregate budget is exhausted, subsequent string/list sources
    # are skipped (not recorded as sources with 0 bytes). Truncation is noted.
    packer = ContextBudgetPacker(ContextBudget(max_bytes=14, max_tokens=4))

    packed, report = packer.pack(
        {
            "project_root": "[PROJECT_ROOT]",
            "files": ["README.md", "src/app.py"],
            "readme": "abcdef",
        }
    )

    assert packed["project_root"] == "[PROJECT_ROOT]"
    assert packed["files"] == []
    assert packed["readme"] == ""
    assert report.bytes_used <= 14
    assert report.tokens_estimated == estimate_tokens_from_bytes(report.bytes_used)
    # After budget exhaustion, skipped sources are not added as source entries.
    source_keys = [source.key for source in report.sources]
    assert "project_root" in source_keys
    # Truncation/skip notes should mention the skipped keys
    notes_text = " ".join(report.truncation_notes)
    assert "files" in notes_text or "readme" in notes_text


def test_budget_packer_truncates_utf8_on_byte_boundary() -> None:
    packed, report = ContextBudgetPacker(ContextBudget(max_bytes=5)).pack({"readme": "你好世界"})

    assert packed["readme"] == "你"
    assert report.sources[0].bytes_used == len("你".encode("utf-8"))
    assert report.sources[0].truncated is True


def test_context_collector_adds_budget_metadata(tmp_path: Path) -> None:
    config = SafeCodeConfig(max_context_chars=35)
    (tmp_path / "README.md").write_text("public text\n" * 20, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    context = ContextCollector(tmp_path, config).collect()

    assert context["context_budget"]["max_bytes"] == 35
    assert context["context_budget"]["bytes_used"] <= 35
    assert context["context_budget"]["sources"]
    assert context["context_budget"]["truncation_notes"]


def test_context_selector_returns_ranked_sources_with_reasons(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "billing_api.py").write_text("", encoding="utf-8")
    (tmp_path / "tests" / "test_billing_api.py").write_text("", encoding="utf-8")
    (tmp_path / "README.md").write_text("", encoding="utf-8")

    sources = ContextSelector(tmp_path).select_sources("billing api", limit=2)

    assert all(isinstance(source, SelectedContextSource) for source in sources)
    assert [source.path for source in sources] == ["src/billing_api.py", "tests/test_billing_api.py"]
    assert sources[0].score == 2
    assert "billing" in sources[0].reason
    assert ContextSelector(tmp_path).select("billing api", limit=1) == ["src/billing_api.py"]
