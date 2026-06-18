"""Governance checks for the consolidated docs structure."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_docs_relative_links_are_valid() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check-doc-links.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "docs_missing_count=0" in result.stdout


def test_docs_entrypoints_exist() -> None:
    required = [
        DOCS / "README.md",
        DOCS / "current-status.md",
        DOCS / "planning-history.md",
        DOCS / "release-ledger.md",
        DOCS / "user-guide.md",
        DOCS / "reference" / "README.md",
        DOCS / "reference" / "commands.md",
        DOCS / "reference" / "version-summary.md",
        DOCS / "tutorials" / "README.md",
        DOCS / "tutorials" / "stack-first-hour.md",
        DOCS / "version-plans" / "README.md",
    ]
    missing = [path for path in required if not path.is_file()]
    assert missing == []


def test_docs_root_stays_curated() -> None:
    root_docs = sorted(path.name for path in DOCS.glob("*.md"))
    assert "README.md" in root_docs
    assert len(root_docs) <= 20, root_docs


def test_reference_index_links_to_key_reference_pages() -> None:
    text = _read(DOCS / "reference" / "README.md")
    for target in (
        "commands.md",
        "version-summary.md",
        "../public-contracts.md",
        "../providers.md",
        "../context-budgets.md",
        "../version_implementation_matrix.md",
    ):
        assert target in text


def test_tutorial_index_uses_shared_stack_first_hour() -> None:
    text = _read(DOCS / "tutorials" / "README.md")
    assert "stack-first-hour.md" in text
    assert "python-first-hour.md" not in text
    assert "typescript-first-hour.md" not in text
    assert "go-first-hour.md" not in text


def test_release_ledger_covers_current_baseline() -> None:
    text = _read(DOCS / "release-ledger.md")
    assert "## v7.1.5" in text
    assert "## v7.0.0" in text
    assert "## v6.0.0" in text


def test_version_summary_points_to_current_baseline_and_matrix() -> None:
    text = _read(DOCS / "reference" / "version-summary.md")
    assert "v7.1.5" in text
    assert "../release-ledger.md" in text
    assert "../version_implementation_matrix.md" in text
    assert "../current-status.md" in text


def test_version_plans_index_marks_v70_followup_historical() -> None:
    index_text = _read(DOCS / "version-plans" / "README.md")
    assert "No active version plan" in index_text
    assert "_template.md" in index_text
    assert "../planning-history.md" in index_text

    plan_text = _read(DOCS / "planning-history.md")
    for version in ("v7.0.1", "v7.0.2", "v7.0.3", "v7.0.4"):
        assert version in plan_text
