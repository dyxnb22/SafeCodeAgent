"""Tests for consolidated product security review documentation."""

from pathlib import Path


DOC = Path("docs/security/threat-model-v3.6.md")


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_security_review_doc_exists() -> None:
    assert DOC.is_file()


def test_security_review_covers_required_sections() -> None:
    text = _text()
    for heading in (
        "### Configuration Policy",
        "### Sandbox Defaults",
        "### Hooks",
        "### Release Gates",
        "### Trust Boundaries",
    ):
        assert heading in text


def test_security_review_mentions_policy_audit_and_release_preflight() -> None:
    text = _text()
    assert "sac config policy-audit" in text
    assert "sac release preflight" in text


def test_security_review_documents_project_cannot_lower_user_safety() -> None:
    text = _text().lower()
    assert "project-local configuration cannot lower user-level safety" in text


def test_security_review_documents_tag_metadata_boundary() -> None:
    text = _text()
    assert "Release tags are not trusted" in text
    assert "safecode.__version__" in text
