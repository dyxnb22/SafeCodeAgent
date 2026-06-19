"""GA security review document contract tests (v3.0.2-T1)."""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_REVIEW = _ROOT / "enterprise-docs" / "security" / "security-review-v3.0.md"
_SECURITY_CHECK = _ROOT / "examples" / "enterprise" / "demos" / "v3.0" / "security_check.md"
_THREAT_MODEL = _ROOT / "enterprise-docs" / "security" / "threat-model-v2.5.md"

_FORBIDDEN_TOKENS = ("ghp_", "gho_", "sk-", "password=")


def _read(path: Path) -> str:
    assert path.is_file(), f"missing required artifact: {path}"
    return path.read_text(encoding="utf-8")


def test_ga_security_review_document_exists() -> None:
    text = _read(_REVIEW)
    assert "## Independent Sign-off" in text
    assert "## Findings Summary" in text


def test_ga_security_review_references_threat_model_v2_5() -> None:
    review = _read(_REVIEW)
    assert "threat-model-v2.5.md" in review
    assert _THREAT_MODEL.is_file()


def test_ga_security_review_has_no_open_high_or_critical_findings() -> None:
    text = _read(_REVIEW)
    for line in text.splitlines():
        if not line.startswith("| GA-"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        _finding_id, severity, _topic, status = cells[:4]
        if status.upper() == "OPEN" and severity.upper() in {"HIGH", "CRITICAL"}:
            raise AssertionError(f"open high/critical finding: {line}")


def test_ga_security_review_sign_off_block_present() -> None:
    text = _read(_REVIEW)
    assert re.search(r"Security reviewer", text)
    assert "Pending independent reviewer" in text
    assert "PENDING" in text


def test_security_check_does_not_claim_external_gates_are_green() -> None:
    text = _read(_SECURITY_CHECK)
    assert "BLOCKED" in text
    assert "Independent review and detached signature" in text


def test_candidate_review_cannot_claim_ga_pass_without_external_signoff() -> None:
    text = _read(_REVIEW)
    assert "Not approved for GA" in text
    assert "Verdict:** Pass" not in text
    assert "sha256:enterprise-ga" not in text


def test_security_artifacts_contain_no_secret_material() -> None:
    for path in (_REVIEW, _SECURITY_CHECK):
        serialized = _read(path)
        for token in _FORBIDDEN_TOKENS:
            assert token not in serialized, f"{path.name} contains forbidden token {token!r}"
