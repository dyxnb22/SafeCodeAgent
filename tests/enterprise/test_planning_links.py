"""Verify local path references in portfolio narrative documents."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent

SCANNED_DOCS = (
    "product-planning/case-study-secure-change-platform.md",
    "product-planning/interview-master-narrative.md",
    "product-planning/post-ga-portfolio-roadmap.md",
    "README.md",
)

PATH_PREFIXES = (
    "src/",
    "tests/",
    "product-planning/",
    "enterprise-docs/",
    "examples/",
    "docs/",
)

# `path/to/file.py` or `path/to/dir/` inside backticks.
_BACKTICK_PATH = re.compile(r"`((?:" + "|".join(PATH_PREFIXES) + r")[^`\s]+)`")


def _extract_paths(text: str) -> set[str]:
    paths: set[str] = set()
    for match in _BACKTICK_PATH.findall(text):
        candidate = match.strip().rstrip(".,;:")
        if candidate.startswith(("http://", "https://")):
            continue
        paths.add(candidate)
    return paths


def _resolve_exists(relative: str) -> bool:
    path = _ROOT / relative
    if path.is_file() or path.is_dir():
        return True
    # Allow directory references written without trailing slash.
    if (path.parent / path.name).exists():
        return True
    return False


@pytest.mark.parametrize("relative_doc", SCANNED_DOCS)
def test_planning_document_paths_exist(relative_doc: str) -> None:
    doc_path = _ROOT / relative_doc
    assert doc_path.is_file(), f"missing scanned document: {relative_doc}"
    missing: list[str] = []
    text = doc_path.read_text(encoding="utf-8")
    for ref in sorted(_extract_paths(text)):
        if not _resolve_exists(ref):
            missing.append(ref)
    assert not missing, (
        f"{relative_doc} references missing paths:\n" + "\n".join(missing)
    )


def test_architecture_poster_exists() -> None:
    poster = _ROOT / "docs/architecture-poster.md"
    assert poster.is_file()
    assert poster.read_text(encoding="utf-8").startswith("# ")
