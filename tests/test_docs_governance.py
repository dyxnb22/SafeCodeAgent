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
        DOCS / "archive" / "README.md",
        DOCS / "reference" / "README.md",
        DOCS / "reference" / "commands.md",
        DOCS / "reference" / "version-summary.md",
        DOCS / "tutorials" / "README.md",
        DOCS / "tutorials" / "stack-first-hour.md",
        DOCS / "version-notes" / "README.md",
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
    stack_idx = text.index("stack-first-hour.md")
    python_idx = text.index("python-first-hour.md")
    ts_idx = text.index("typescript-first-hour.md")
    go_idx = text.index("go-first-hour.md")
    assert stack_idx < python_idx < ts_idx < go_idx


def test_version_notes_index_covers_major_trains_and_links_exist() -> None:
    index = DOCS / "version-notes" / "README.md"
    text = _read(index)
    for major in ("v0", "v1", "v2", "v3", "v4"):
        assert f"| {major} |" in text

    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = target.split("#", 1)[0]
        if not target or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        assert (index.parent / target).resolve().exists(), target


def test_version_summary_points_to_current_baseline_and_matrix() -> None:
    text = _read(DOCS / "reference" / "version-summary.md")
    assert "v4.14.0" in text
    assert "../version-plans/post-v4.14-usability-roadmap.md" in text
    assert "../version_implementation_matrix.md" in text
    assert "../project-final-status-and-roadmap.md" in text
