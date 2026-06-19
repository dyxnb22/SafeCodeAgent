"""Prompt-injection eval suite tests."""

from pathlib import Path

from safecode.enterprise.eval.loader import discover_cases
from safecode.enterprise.eval.runner import run_suite

_ROOT = Path(__file__).resolve().parents[3]
_CASES = Path(__file__).resolve().parent / "cases"


def test_prompt_injection_suite_has_eight_categories():
    cases = discover_cases(_CASES, suite="prompt_injection")
    assert len(cases) >= 8


def test_prompt_injection_suite_passes_under_mock_provider():
    cases = discover_cases(_CASES, suite="prompt_injection")
    results = run_suite(cases, project_root=_ROOT)
    failures = [item for item in results if not item.passed]
    assert not failures, failures
