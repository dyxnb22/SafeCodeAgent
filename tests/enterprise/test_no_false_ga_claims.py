"""Guard against unconditional false enterprise GA claims in portfolio docs."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.enterprise.markdown_doc_scan import (
    documentation_surface_paths,
    repo_root,
)

_ROOT = repo_root()

FORBIDDEN_PHRASES = (
    "GA approved",
    "general availability approved",
    "externally signed",
    "externally signed off",
    "external sign-off complete",
    "signed external review complete",
    "signed off for production",
    "production deployed",
    "production deployment complete",
    "production-ready",
    "production ready",
    "ready for production",
    "GA-ready",
    "GA ready",
    "approved for production",
    "deployment ready",
    "enterprise certified",
    "live provider evidence complete",
    "no open yellow risks",
    "G1 approved",
    "G2 approved",
    "G3 approved",
    "SOC 2 certified",
    "ISO 27001 certified",
    "external audit passed",
    "blocker resolved",
)

ALLOWED_CONTEXT = re.compile(
    r"(?:\bnot\b|\bno\b|\bnever\b|\bcannot\b|\bcan't\b|\bmust not\b|"
    r"\bdoes not\b|\bdo not\b|\bwithout\b)[^.;!?|]{0,60}$|"
    r"\bany document that (?:says|uses)\b[^.;!?|]*$",
    re.IGNORECASE,
)

CLAUSE_BOUNDARY = re.compile(
    r"[.;!?|]|\u2014|,\s*(?:but|yet|however)\b|"
    r"\b(?:but|yet|however|although|whereas)\b",
    re.IGNORECASE,
)

REQUIRED_SCAN_PREFIXES = (
    "README.md",
    "docs/",
    "enterprise-docs/",
    ".agents/",
    "product-planning/",
)


def _phrase_allowed(line: str, phrase: str) -> bool:
    matches = list(re.finditer(re.escape(phrase), line, re.IGNORECASE))
    if not matches:
        return True
    boundaries = list(CLAUSE_BOUNDARY.finditer(line))
    for match in matches:
        left = max(
            (boundary.end() for boundary in boundaries if boundary.end() <= match.start()),
            default=0,
        )
        prefix = line[left : match.start()]
        if not ALLOWED_CONTEXT.search(prefix):
            return False
    return True


def _scan_file(path: Path) -> list[str]:
    relative = path.relative_to(_ROOT).as_posix()
    violations: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") and phrase_only_heading(stripped):
            continue
        for phrase in FORBIDDEN_PHRASES:
            if phrase.lower() not in line.lower():
                continue
            if not _phrase_allowed(line, phrase):
                violations.append(f"{relative}:{line_number}: {phrase!r} in {line!r}")
    return violations


def phrase_only_heading(line: str) -> bool:
    """Skip pure headings that do not make standalone claims."""
    body = line.lstrip("#").strip()
    return not any(phrase.lower() in body.lower() for phrase in FORBIDDEN_PHRASES)


def test_false_ga_scan_covers_documentation_surfaces() -> None:
    surfaces = documentation_surface_paths()
    assert surfaces
    for prefix in REQUIRED_SCAN_PREFIXES:
        assert any(path == prefix or path.startswith(prefix) for path in surfaces), prefix


@pytest.mark.parametrize(
    "line",
    [
        "v3.0 remains blocked; G1/G2/G3 pending.",
        'Do not claim "GA approved" without evidence.',
        "This is not production deployed.",
        "No external sign-off has been recorded.",
        "Portfolio demo only; offline simulation.",
        'Any document that says the project is "GA approved" needs evidence.',
    ],
)
def test_allowed_negative_and_pending_contexts(line: str) -> None:
    for phrase in FORBIDDEN_PHRASES:
        if phrase.lower() in line.lower():
            assert _phrase_allowed(line, phrase), (line, phrase)


@pytest.mark.parametrize(
    "line,phrase",
    [
        ("Enterprise GA approved for all tenants.", "GA approved"),
        ("The platform is production deployed today.", "production deployed"),
        ("External audit passed and G1 approved.", "G1 approved"),
        ('The platform is "GA approved".', "GA approved"),
        ("G1 remains pending, but the platform is GA approved.", "GA approved"),
        ("Not production deployed, but it is production-ready.", "production-ready"),
        ("The platform is ready for production.", "ready for production"),
    ],
)
def test_forbidden_claims_are_detected(line: str, phrase: str) -> None:
    assert not _phrase_allowed(line, phrase)


@pytest.mark.parametrize("relative_path", documentation_surface_paths())
def test_no_unqualified_false_ga_claims(relative_path: str) -> None:
    path = _ROOT / relative_path
    assert path.is_file(), f"missing scanned document: {relative_path}"
    violations = _scan_file(path)
    assert not violations, "unqualified false GA claims found:\n" + "\n".join(violations)


def test_scanner_includes_release_notes() -> None:
    assert "RELEASE-NOTES-v3.0.0.md" in documentation_surface_paths()
