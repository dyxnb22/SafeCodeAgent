"""Tests for the explainable unified memory read pipeline."""

from safecode.memory.facade import MemoryFacade
from safecode.memory.facts import ProjectFactStore
from safecode.memory.ledger import ContextLedger


def test_ledger_drives_injected_context_and_explanation(tmp_path):
    facts = ProjectFactStore(tmp_path / ".sac")
    proposed = facts.propose("test_command", "pytest -q", source="user")
    assert proposed is not None
    facts.approve(proposed.fact_id)
    MemoryFacade(tmp_path).add_note("Prefer focused unit tests.")

    ledger = ContextLedger(tmp_path)
    context = ledger.injected_context()
    explanation = ledger.explain()

    assert "pytest -q" in context
    assert "Prefer focused unit tests" in context
    assert "approved facts: injected" in explanation
    assert "pending facts: not injected" in explanation


def test_pending_fact_is_explained_but_not_injected(tmp_path):
    facts = ProjectFactStore(tmp_path / ".sac")
    facts.propose("convention", "untrusted pending instruction", source="auto")

    ledger = ContextLedger(tmp_path)

    assert "untrusted pending instruction" not in ledger.injected_context()
    assert "requires explicit approval" in ledger.explain()
