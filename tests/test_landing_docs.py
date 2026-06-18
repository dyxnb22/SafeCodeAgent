"""Tests for v3.6.5 landing documentation."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

WHY = ROOT / "docs" / "why-safecode.md"
TROUBLESHOOTING = ROOT / "docs" / "troubleshooting.md"
README = ROOT / "README.md"


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


def test_why_safecode_exists() -> None:
    assert WHY.is_file()


def test_troubleshooting_exists() -> None:
    assert TROUBLESHOOTING.is_file()


# ---------------------------------------------------------------------------
# comparison content in why-safecode.md
# ---------------------------------------------------------------------------


def test_why_safecode_has_required_headings() -> None:
    text = WHY.read_text(encoding="utf-8")
    for heading in (
        "# Why SafeCode Agent",
        "## The Core Problem",
        "## The Safety Loop",
        "## Key Properties",
        "## What SafeCode Is Not",
        "## Experimental Surfaces",
    ):
        assert heading in text, f"Missing heading: {heading}"


def test_why_safecode_mentions_experimental_surfaces() -> None:
    text = WHY.read_text(encoding="utf-8")
    assert "experimental" in text.lower()
    assert "SafeCodeLocalAPI" in text or "LocalAPI" in text
    assert "MCP" in text


def test_why_safecode_links_to_public_contracts() -> None:
    text = WHY.read_text(encoding="utf-8")
    assert "public-contracts.md" in text


# ---------------------------------------------------------------------------
# why-safecode.md headings and content
# ---------------------------------------------------------------------------


def test_compare_has_required_headings() -> None:
    text = WHY.read_text(encoding="utf-8")
    for heading in (
        "## Comparison",
        "## Capability Summary",
    ):
        assert heading in text, f"Missing heading: {heading}"


def test_compare_mentions_stable_and_experimental() -> None:
    text = WHY.read_text(encoding="utf-8")
    assert "Stable" in text
    assert "Experimental" in text


def test_compare_links_to_public_contracts() -> None:
    text = WHY.read_text(encoding="utf-8")
    assert "public-contracts.md" in text


def test_compare_does_not_overclaim_sandbox() -> None:
    text = WHY.read_text(encoding="utf-8").lower()
    assert "preview" in text or "experimental" in text


# ---------------------------------------------------------------------------
# troubleshooting.md headings and content
# ---------------------------------------------------------------------------


def test_troubleshooting_has_required_headings() -> None:
    text = TROUBLESHOOTING.read_text(encoding="utf-8")
    for heading in (
        "# Troubleshooting SafeCode Agent",
        "## Diagnostics First",
        "## Common Issues",
        "## Runtime Logs",
    ):
        assert heading in text, f"Missing heading: {heading}"


def test_troubleshooting_mentions_sac_doctor() -> None:
    text = TROUBLESHOOTING.read_text(encoding="utf-8")
    assert "sac doctor" in text


def test_troubleshooting_mentions_sac_logs() -> None:
    text = TROUBLESHOOTING.read_text(encoding="utf-8")
    assert "sac logs" in text


def test_troubleshooting_mentions_rollback() -> None:
    text = TROUBLESHOOTING.read_text(encoding="utf-8")
    assert "sac rollback" in text


# ---------------------------------------------------------------------------
# README links
# ---------------------------------------------------------------------------


def test_readme_links_to_why_safecode() -> None:
    text = README.read_text(encoding="utf-8")
    assert "docs/why-safecode.md" in text


def test_readme_links_to_compare() -> None:
    text = README.read_text(encoding="utf-8")
    assert "docs/why-safecode.md" in text


def test_readme_links_to_troubleshooting() -> None:
    text = README.read_text(encoding="utf-8")
    assert "docs/troubleshooting.md" in text


# Per-stack tutorial claims are guarded in tests/test_docs_claims_guard.py.
