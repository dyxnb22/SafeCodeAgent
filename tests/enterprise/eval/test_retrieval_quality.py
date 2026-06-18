"""Retrieval quality eval tests (v1.1.4-T2)."""

from pathlib import Path

from safecode.enterprise.eval.retrieval import compare_with_baseline, run_suite

_ROOT = Path(__file__).resolve().parents[3]
_CASE_DIR = Path(__file__).resolve().parent / "cases" / "retrieval"
_MANIFEST = _ROOT / "examples/enterprise/knowledge_sources.yaml"
_BASELINE = Path(__file__).resolve().parent / "baselines" / "retrieval_v1_1.json"


def test_retrieval_eval_suite_meets_baseline():
    case_paths = sorted(_CASE_DIR.glob("*.yaml"))
    results = run_suite(case_paths, _MANIFEST, _ROOT)
    failures = compare_with_baseline(results, _BASELINE)
    assert not failures, failures


def test_forbidden_sources_never_appear_in_results():
    case_paths = sorted(_CASE_DIR.glob("*.yaml"))
    results = run_suite(case_paths, _MANIFEST, _ROOT)
    assert all(not result.forbidden_hits for result in results)
