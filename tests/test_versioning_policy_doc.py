"""Tests for v3.9.1 T-3.99.0-B: versioning policy document.

Verifies that docs/versioning-policy.md exists and documents the required
patch/minor/major semantics and the v4.0 churn budget.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_POLICY_DOC = Path(__file__).parent.parent / "docs" / "versioning-policy.md"


def _load() -> str:
    return _POLICY_DOC.read_text(encoding="utf-8")


class TestVersioningPolicyDocExists:
    def test_doc_exists(self):
        assert _POLICY_DOC.exists(), f"docs/versioning-policy.md not found"

    def test_doc_nonempty(self):
        assert len(_load()) > 100


class TestPatchSemanticsDocumented:
    def test_patch_never_changes_public_contracts_phrase(self):
        assert "Patch never changes public contracts" in _load()

    def test_patch_never_changes_contract(self):
        content = _load()
        assert "patch" in content.lower()
        # patch must claim contract stability
        assert "never" in content.lower() or "no" in content.lower()

    def test_patch_section_present(self):
        content = _load()
        assert "Patch" in content or "patch" in content


class TestMinorSemanticsDocumented:
    def test_minor_may_add_experimental_phrase(self):
        assert "Minor may add experimental surfaces" in _load()

    def test_minor_may_add_experimental(self):
        content = _load()
        assert "minor" in content.lower() or "Minor" in content
        assert "experimental" in content.lower()

    def test_minor_no_breaking(self):
        content = _load()
        lower = content.lower()
        assert "never" in lower or "breaking" in lower


class TestMajorSemanticsDocumented:
    def test_major_reserved_for_public_contract_changes_phrase(self):
        assert "Major is reserved for public contract changes" in _load()

    def test_major_required_for_breaking(self):
        content = _load()
        assert "major" in content.lower() or "Major" in content
        assert "breaking" in content.lower() or "break" in content


class TestV40ChurnBudget:
    def test_v40_exact_churn_budget_language(self):
        content = _load()
        assert "At most two new stable contracts" in content
        assert "Zero breaking changes" in content

    def test_v40_churn_budget_present(self):
        content = _load()
        assert "v4.0" in content or "4.0" in content

    def test_at_most_two_new_stable_contracts(self):
        content = _load()
        lower = content.lower()
        assert "two" in lower or "2" in lower

    def test_zero_breaking_changes_to_v30_contracts(self):
        content = _load()
        lower = content.lower()
        assert "zero" in lower or "no breaking" in lower

    def test_v30_contracts_referenced(self):
        content = _load()
        assert "v3.0" in content


class TestBrewDecisionDocumented:
    def test_brew_decision_documented(self):
        content = _load()
        lower = content.lower()
        assert "brew" in lower or "homebrew" in lower

    def test_brew_strategy_is_defer_or_tap_or_formula(self):
        content = _load()
        lower = content.lower()
        assert "defer" in lower or "tap" in lower or "formula" in lower


class TestREADMELinksPolicy:
    def test_readme_links_versioning_policy(self):
        readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
        assert "versioning-policy" in readme or "versioning_policy" in readme, (
            "README.md should link to docs/versioning-policy.md"
        )
