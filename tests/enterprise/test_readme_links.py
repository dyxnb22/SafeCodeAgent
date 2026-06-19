"""Verify internal Markdown links in the root README."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
README = _ROOT / "README.md"

# [label](target) and [label](target "title")
_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _iter_internal_targets(text: str) -> list[str]:
    targets: list[str] = []
    for raw in _LINK.findall(text):
        target = raw.strip().split()[0].strip("<>")
        if not target or target.startswith("#"):
            continue
        parsed = urlparse(target)
        if parsed.scheme in {"http", "https", "mailto"}:
            continue
        path = unquote(parsed.path)
        if not path:
            continue
        targets.append(path)
    return targets


def test_readme_internal_links_resolve() -> None:
    text = README.read_text(encoding="utf-8")
    missing: list[str] = []
    for target in _iter_internal_targets(text):
        candidate = _ROOT / target
        if candidate.is_file() or candidate.is_dir():
            continue
        missing.append(target)
    assert not missing, "README broken internal links:\n" + "\n".join(missing)
