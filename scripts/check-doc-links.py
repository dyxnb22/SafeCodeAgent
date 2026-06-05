#!/usr/bin/env python3
"""Check relative Markdown links under docs/."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _iter_markdown_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def _link_target(raw: str) -> str:
    return raw.split("#", 1)[0].strip()


def _is_external_or_empty(target: str) -> bool:
    return not target or SCHEME_RE.match(target) is not None


def check_links(root: Path) -> list[tuple[Path, str]]:
    missing: list[tuple[Path, str]] = []
    for path in _iter_markdown_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in LINK_RE.finditer(text):
            target = _link_target(match.group(1))
            if _is_external_or_empty(target):
                continue
            if not (path.parent / target).resolve().exists():
                missing.append((path, target))
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        default="docs",
        help="Markdown documentation root to scan. Default: docs",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        print(f"docs link check failed: root does not exist: {root}", file=sys.stderr)
        return 2

    missing = check_links(root)
    for path, target in missing:
        print(f"{path}: missing {target}")
    print(f"docs_missing_count={len(missing)}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
