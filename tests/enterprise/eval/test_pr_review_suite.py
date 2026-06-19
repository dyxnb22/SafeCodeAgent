"""PR review eval suite tests."""

from pathlib import Path

from safecode.enterprise.eval.loader import discover_cases
from safecode.enterprise.eval.runner import run_suite

_ROOT = Path(__file__).resolve().parents[3]
_CASES = Path(__file__).resolve().parent / "cases"


def test_pr_review_eval_suite_has_five_cases():
    cases = discover_cases(_CASES, suite="pr_review")
    assert len(cases) == 5


def test_pr_review_eval_suite_passes():
    cases = discover_cases(_CASES, suite="pr_review")
    results = run_suite(cases, project_root=_ROOT)
    assert len(results) == 5
    assert all(item.passed for item in results), [item.case_id for item in results if not item.passed]
