"""Shared helpers for enterprise documentation link and claim scans."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

_ROOT = Path(__file__).resolve().parent.parent.parent

DOC_MARKDOWN_GLOBS = (
    "README.md",
    "RELEASE-NOTES*.md",
    "docs/**/*.md",
    "enterprise-docs/**/*.md",
    ".agents/**/*.md",
    "product-planning/**/*.md",
)

BACKTICK_PATH_PREFIXES = (
    "src/",
    "tests/",
    "product-planning/",
    "enterprise-docs/",
    "examples/",
    "docs/",
    ".agents/",
)

MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_BACKTICK_PATH = re.compile(
    r"`((?:" + "|".join(re.escape(prefix) for prefix in BACKTICK_PATH_PREFIXES) + r")[^`\s]+)`"
)
_LINE_SUFFIX = re.compile(r":\d+(?::\d+)?$")
_TEMPLATE_MARKERS = re.compile(r"[*<>{}?]")


def repo_root() -> Path:
    return _ROOT


def iter_documentation_markdown_files() -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in DOC_MARKDOWN_GLOBS:
        if any(marker in pattern for marker in ("*", "?", "[")):
            matches = sorted(_ROOT.glob(pattern))
        else:
            candidate = _ROOT / pattern
            matches = [candidate] if candidate.is_file() else []
        for path in matches:
            resolved = path.resolve()
            if resolved in seen or not path.is_file():
                continue
            seen.add(resolved)
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(_ROOT).as_posix())


def documentation_surface_paths() -> list[str]:
    return [path.relative_to(_ROOT).as_posix() for path in iter_documentation_markdown_files()]


def iter_internal_markdown_link_targets(text: str) -> list[str]:
    targets: list[str] = []
    for raw in MARKDOWN_LINK.findall(text):
        value = raw.strip()
        if value.startswith("<") and ">" in value:
            target = value[1 : value.index(">")]
        else:
            target = value.split(maxsplit=1)[0]
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


def normalize_backtick_path(raw: str) -> str:
    candidate = raw.strip().rstrip(".,;:")
    candidate = _LINE_SUFFIX.sub("", candidate)
    return candidate


def backtick_reference_is_verifiable(
    line: str,
    ref: str,
    *,
    start: int | None = None,
    end: int | None = None,
) -> bool:
    if _TEMPLATE_MARKERS.search(ref):
        return False
    if start is None or end is None:
        start = line.find(ref)
        end = start + len(ref)
    left = max(line.rfind(";", 0, start), line.rfind("|", 0, start)) + 1
    boundaries = [position for position in (line.find(";", end), line.find("|", end)) if position >= 0]
    right = min(boundaries, default=len(line))
    lower = line[left:right].lower()
    if any(
        marker in lower
        for marker in (
            "removed from",
            "already removed",
            "no longer",
            "not retained",
            "do not recreate",
            "legacy `",
            "original product",
        )
    ):
        return False
    return True


def iter_backtick_path_references(text: str) -> set[str]:
    paths: set[str] = set()
    for line in text.splitlines():
        for match in _BACKTICK_PATH.finditer(line):
            candidate = normalize_backtick_path(match.group(1))
            if candidate.startswith(("http://", "https://")):
                continue
            if not backtick_reference_is_verifiable(
                line,
                candidate,
                start=match.start(),
                end=match.end(),
            ):
                continue
            paths.add(candidate)
    return paths


def path_exists_in_repo(relative: str) -> bool:
    candidate = Path(relative)
    if candidate.is_absolute():
        return False
    path = (_ROOT / candidate).resolve()
    try:
        path.relative_to(_ROOT.resolve())
    except ValueError:
        return False
    return path.is_file() or path.is_dir()


def internal_markdown_target_exists(document: Path, target: str) -> bool:
    """Resolve a Markdown target relative to its containing document."""
    candidate = Path(target)
    if candidate.is_absolute():
        return False
    path = (document.parent / candidate).resolve()
    try:
        path.relative_to(_ROOT.resolve())
    except ValueError:
        return False
    return path.is_file() or path.is_dir()
