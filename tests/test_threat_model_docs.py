"""Tests for v3.6.4 threat model documentation."""

from pathlib import Path


DOC = Path("docs/security/threat-model-v3.6.md")


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_threat_model_doc_exists() -> None:
    assert DOC.is_file()


def test_threat_model_covers_local_user() -> None:
    assert "### Local User" in _text()


def test_threat_model_covers_malicious_repo() -> None:
    assert "### Malicious Repo" in _text()


def test_threat_model_covers_malicious_project_config() -> None:
    assert "### Malicious Project Config" in _text()


def test_threat_model_covers_malicious_mcp_server() -> None:
    assert "### Malicious MCP Server" in _text()


def test_threat_model_covers_malicious_model_output() -> None:
    assert "### Malicious Model Output" in _text()


def test_threat_model_covers_network_provider_risk() -> None:
    assert "### Network and Provider Risk" in _text()


def test_threat_model_covers_audit_approval_trust_boundaries() -> None:
    assert "### Audit and Approval Trust Boundaries" in _text()


def test_threat_model_covers_sandbox_limitations() -> None:
    assert "### Sandbox Limitations" in _text()


def test_threat_model_covers_telemetry_guarantees() -> None:
    assert "### Telemetry and Update-Check Guarantees" in _text()


def test_threat_model_mentions_review_cadence() -> None:
    text = _text()
    assert "semi-annual" in text.lower() or "review cadence" in text.lower()


def test_threat_model_mentions_project_cannot_lower_safety() -> None:
    text = _text().lower()
    assert "project" in text and "cannot lower" in text


def test_threat_model_mentions_audit_hash_chain() -> None:
    text = _text().lower()
    assert "sha-256" in text or "hash chain" in text or "hash-chain" in text


def test_threat_model_mentions_network_disabled_by_default() -> None:
    text = _text().lower()
    assert "disabled by default" in text
