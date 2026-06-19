"""Ratchet enforcement tests."""

import json
from pathlib import Path

from safecode.enterprise.eval.cases import EvaluationResult
from safecode.enterprise.eval.ratchet import check_ratchet, write_baseline


def test_ratchet_fails_when_pass_rate_regresses(tmp_path: Path):
    baseline = tmp_path / "suite.json"
    write_baseline(
        [EvaluationResult(case_id="smoke.pass_through", suite="smoke", passed=True)],
        baseline,
        commit="abc",
        recorded_at="2026-06-19",
    )
    failures = check_ratchet(
        [EvaluationResult(case_id="smoke.pass_through", suite="smoke", passed=False)],
        baseline,
    )
    assert failures


def test_update_baseline_includes_commit_and_date(tmp_path: Path):
    path = write_baseline(
        [EvaluationResult(case_id="smoke.pass_through", suite="smoke", passed=True)],
        tmp_path / "smoke.json",
        commit="deadbeef",
        recorded_at="2026-06-19",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["commit"] == "deadbeef"
    assert payload["date"] == "2026-06-19"
