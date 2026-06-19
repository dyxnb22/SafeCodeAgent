"""Guard against unconditional false enterprise GA claims in key docs."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent

SCANNED_FILES = (
    "README.md",
    "RELEASE-NOTES-v3.0.0.md",
    "enterprise-docs/security/security-review-v3.0.md",
    "enterprise-docs/security/external-gates.md",
    "product-planning/post-ga-portfolio-roadmap.md",
)

FORBIDDEN_PHRASES = (
    "GA approved",
    "externally signed",
    "signed external review complete",
    "production deployed",
    "production deployment complete",
    "live provider evidence complete",
    "no open yellow risks",
)

ALLOWED_CONTEXT = re.compile(
    r"(?:\bnot\b|\bno\b|\bnever\b|\bcannot\b|\bcan't\b|\bmust not\b|"
    r"\bdoes not\b|\bdo not\b|\bwithout\b|\bremain[s]?\b|\bpending\b|"
    r"\bblocked\b|\brequired\b|\bcandidate\b|\bportfolio final\b|"
    r"\bnot approved\b|\bmust not be\b|\bdo not claim\b|\bnot close\b|"
    r"\bnot satisfied\b|\bnot imply\b|\bnot mark\b|\bnot convert\b|"
    r"\bnot represent\b|\bnot add\b|\bnot approved for\b)",
    re.IGNORECASE,
)


def _phrase_allowed(line: str, phrase: str) -> bool:
    if f'"{phrase}"' in line or f"'{phrase}'" in line:
        return True
    lower = line.lower()
    start = lower.find(phrase.lower())
    if start < 0:
        return True
    window = line[max(0, start - 60) : start + len(phrase) + 40]
    return bool(ALLOWED_CONTEXT.search(window))


@pytest.mark.parametrize("relative_path", SCANNED_FILES)
def test_no_unqualified_false_ga_claims(relative_path: str) -> None:
    path = _ROOT / relative_path
    assert path.is_file(), f"missing scanned document: {relative_path}"
    violations: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for phrase in FORBIDDEN_PHRASES:
            if phrase.lower() not in line.lower():
                continue
            if not _phrase_allowed(line, phrase):
                violations.append(f"{relative_path}:{line_number}: {phrase!r} in {line!r}")
    assert not violations, "unqualified false GA claims found:\n" + "\n".join(violations)
