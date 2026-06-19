"""Ratchet tests for remediation baseline."""

from pathlib import Path

from safecode.enterprise.eval.loader import discover_cases
from safecode.enterprise.eval.ratchet import baseline_path_for_suite, check_ratchet
from safecode.enterprise.eval.runner import run_suite

_ROOT = Path(__file__).resolve().parents[3]
_CASES = Path(__file__).resolve().parent / "cases"
_BASELINES = Path(__file__).resolve().parent / "baselines"


def test_remediation_baseline_ratchet_passes():
    cases = discover_cases(_CASES, suite="remediation")
    results = run_suite(cases, project_root=_ROOT)
    baseline = baseline_path_for_suite(_BASELINES, "remediation")
    assert baseline is not None
    failures = check_ratchet(results, baseline)
    assert not failures, failures
