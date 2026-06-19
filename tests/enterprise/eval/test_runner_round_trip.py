"""Eval runner round-trip tests."""

import time
from pathlib import Path

from safecode.enterprise.eval.loader import discover_cases, load_case_file
from safecode.enterprise.eval.runner import run_case, run_suite, write_results

_CASES_ROOT = Path(__file__).resolve().parent / "cases"
_ROOT = Path(__file__).resolve().parents[3]


def test_smoke_case_runs_in_under_two_seconds(tmp_path: Path):
    case = load_case_file(_CASES_ROOT / "smoke" / "pass_through.yaml")
    started = time.monotonic()
    result = run_case(case, project_root=_ROOT)
    elapsed = time.monotonic() - started
    assert elapsed < 2.0
    assert result.passed is True
    assert result.suite == "smoke"


def test_discover_and_run_smoke_suite(tmp_path: Path):
    cases = discover_cases(_CASES_ROOT, suite="smoke")
    results = run_suite(cases, project_root=_ROOT)
    assert len(results) == 1
    assert all(item.passed for item in results)


def test_write_results_to_sac(tmp_path: Path):
    case = load_case_file(_CASES_ROOT / "smoke" / "pass_through.yaml")
    result = run_case(case, project_root=_ROOT)
    path = write_results([result], tmp_path / ".sac", "eval-run-0001")
    assert path.is_file()
    assert "smoke.pass_through" in path.read_text(encoding="utf-8")
