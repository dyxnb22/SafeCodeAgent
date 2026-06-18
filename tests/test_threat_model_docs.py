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


def test_threat_model_mentions_executor_preflight_promotion_state() -> None:
    text = _text()
    assert "sac sandbox executor-preflight <backend>" in text
    assert "SAFECODE_SANDBOX_DOCKER=1" in text
    assert "SAFECODE_SANDBOX_SEATBELT=1" in text
    assert "SAFECODE_SANDBOX_BUBBLEWRAP=1" in text


def test_threat_model_sandbox_default_remains_noop() -> None:
    text = _text().lower()
    assert "default recommendation remains noop" in text


# ---------------------------------------------------------------------------
# v5.7.0: Semi-annual review extensions
# ---------------------------------------------------------------------------


def test_threat_model_review_has_v570_section() -> None:
    text = _text()
    assert "v5.7.0 Semi-Annual Review" in text or "v5.7.0" in text


def test_threat_model_covers_trust_modes() -> None:
    text = _text()
    assert "Trust mode" in text or "auto-edit" in text or "full-auto" in text


def test_threat_model_covers_mcp_write_execution() -> None:
    text = _text()
    assert "MCP write execution" in text or "v5.4.1" in text


def test_threat_model_covers_git_context() -> None:
    text = _text()
    assert "git" in text.lower() and "context" in text.lower()


def test_threat_model_covers_parallel_subagents() -> None:
    text = _text()
    assert "Parallel subagent" in text or "parallel" in text.lower()


def test_threat_model_covers_prompt_injection_via_tool_results() -> None:
    text = _text()
    assert "Prompt injection" in text or "tool results" in text


def test_threat_model_covers_native_tool_path_validation() -> None:
    text = _text()
    assert "path validation" in text.lower() or "root-boundary" in text.lower()


def test_threat_model_next_review_updated_to_2027() -> None:
    text = _text()
    assert "2027-06-01" in text


def test_threat_model_review_log_has_v570_entry() -> None:
    text = _text()
    assert "v5.7.0" in text


def test_threat_model_review_cadence_mentions_v570() -> None:
    text = _text().lower()
    assert "v5.7.0" in text.lower() or "5.7.0" in text
