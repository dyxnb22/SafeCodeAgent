"""Tool-classification adversarial suite tests."""

from pathlib import Path

from safecode.enterprise.eval.loader import discover_cases
from safecode.enterprise.eval.runner import run_suite

_ROOT = Path(__file__).resolve().parents[3]
_CASES = Path(__file__).resolve().parent / "cases"


def test_tool_classification_suite_passes():
    cases = discover_cases(_CASES, suite="tool_classification")
    results = run_suite(cases, project_root=_ROOT)
    assert all(result.passed for result in results)
