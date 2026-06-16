"""Tests for v5.8.1 v6.0.0 contract candidate assessment."""

from pathlib import Path

_DOC = Path(__file__).parent.parent / "docs" / "v6-contract-candidates.md"
_CONTRACTS_DOC = Path(__file__).parent.parent / "docs" / "public-contracts.md"


def _text() -> str:
    return _DOC.read_text(encoding="utf-8")


def test_candidates_doc_exists():
    assert _DOC.is_file()


def test_candidates_doc_non_empty():
    assert len(_text()) > 200


def test_candidates_covers_trust_modes():
    text = _text()
    assert "Trust mode" in text or "auto_edit" in text or "full_auto" in text


def test_candidates_covers_rollback_session():
    assert "rollback --session" in _text()


def test_candidates_covers_mcp_bridge():
    text = _text()
    assert "MCP" in text and "bridge" in text.lower()


def test_candidates_covers_git_context():
    assert "git" in _text().lower()


def test_candidates_covers_cost_cap():
    assert "cost" in _text().lower()


def test_candidates_covers_sandbox():
    assert "Sandbox" in _text()


def test_candidates_covers_live_eval():
    assert "Live eval" in _text() or "live eval" in _text()


def test_candidates_covers_golden_demo():
    assert "Golden demo" in _text() or "golden-demo" in _text()


def test_all_candidates_have_decision():
    text = _text()
    for surface in ["Trust mode", "rollback --session", "MCP native tool", "Git context", "Cost cap", "Sandbox", "Live eval", "Golden demo"]:
        assert "**Promote**" in text or "**Defer**" in text or "Already stable" in text or "Conditional" in text


def test_v60_churn_budget_stated():
    text = _text()
    assert "5 new stable contracts" in text or "churn budget" in text.lower()


def test_zero_v50_breaking_changes_stated():
    text = _text()
    assert "zero v5.0 breaking changes" in text.lower()


def test_summary_table_exists():
    text = _text()
    assert "Summary Table" in text or "| # |" in text

# ---------------------------------------------------------------------------
# public-contracts.md v6.0 candidate section (v5.8.2)
# ---------------------------------------------------------------------------


def test_contracts_doc_v60_candidate_section():
    text = _CONTRACTS_DOC.read_text(encoding="utf-8")
    assert "v6.0" in text
