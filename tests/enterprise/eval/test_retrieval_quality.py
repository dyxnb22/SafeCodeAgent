"""Retrieval quality eval tests (v1.1.4-T2, migrated v1.6.2)."""

from pathlib import Path

from safecode.enterprise.eval.loader import discover_cases
from safecode.enterprise.eval.retrieval import compare_with_baseline
from safecode.enterprise.eval.runner import run_suite

_ROOT = Path(__file__).resolve().parents[3]
_CASE_DIR = Path(__file__).resolve().parent / "cases"
_MANIFEST = _ROOT / "examples" / "enterprise" / "knowledge_sources.yaml"
_BASELINE = Path(__file__).resolve().parent / "baselines" / "retrieval_v1_1.json"


def test_retrieval_eval_suite_meets_baseline():
    cases = discover_cases(_CASE_DIR, suite="retrieval")
    results = run_suite(cases, project_root=_ROOT, manifest_path=_MANIFEST)
    failures = compare_with_baseline(results, _BASELINE)
    assert not failures, failures


def test_forbidden_sources_never_appear_in_results():
    cases = discover_cases(_CASE_DIR, suite="retrieval")
    results = run_suite(cases, project_root=_ROOT, manifest_path=_MANIFEST)
    assert all(not result.forbidden_behavior_triggered for result in results)
