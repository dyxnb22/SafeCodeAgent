"""Eval baseline ratchet enforcement."""

from __future__ import annotations

import json
from pathlib import Path

from safecode.enterprise.eval.cases import EvaluationResult
from safecode.enterprise.eval.retrieval import compare_with_baseline


class RatchetViolationError(Exception):
    """Raised when results regress below the checked-in baseline."""


def load_baseline(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def baseline_path_for_suite(baselines_root: Path, suite: str) -> Path | None:
    if suite == "retrieval":
        return baselines_root / "retrieval_v1_1.json"
    candidate = baselines_root / f"{suite}_v1_6.json"
    if candidate.is_file():
        return candidate
    matches = sorted(baselines_root.glob(f"{suite}_v*.json"))
    return matches[0] if matches else None


def check_ratchet(
    results: list[EvaluationResult],
    baseline_path: Path,
    *,
    tolerance: float = 0.02,
) -> list[str]:
    if results and results[0].suite == "retrieval":
        return compare_with_baseline(results, baseline_path, tolerance=tolerance)
    baseline = load_baseline(baseline_path)
    failures: list[str] = []
    by_id = {item["case_id"]: item for item in baseline.get("cases", [])}
    for result in results:
        expected = by_id.get(result.case_id)
        if expected is None:
            failures.append(f"missing baseline entry for {result.case_id}")
            continue
        if not result.passed and expected.get("passed", True):
            failures.append(f"{result.case_id} regressed to failed")
        for metric_name, floor in expected.get("metrics", {}).items():
            actual = float(result.metrics.get(metric_name, 0.0))
            if actual + 1e-9 < float(floor) - tolerance:
                failures.append(f"{result.case_id}.{metric_name} below baseline")
        if result.forbidden_behavior_triggered and expected.get("forbidden_behavior_triggered_eq") == []:
            failures.append(f"{result.case_id} triggered forbidden behavior")
    return failures


def write_baseline(
    results: list[EvaluationResult],
    baseline_path: Path,
    *,
    commit: str,
    recorded_at: str,
) -> Path:
    payload = {
        "suite": results[0].suite if results else baseline_path.stem,
        "date": recorded_at,
        "commit": commit,
        "cases": [
            {
                "case_id": item.case_id,
                "passed": item.passed,
                "metrics": item.metrics,
                "forbidden_behavior_triggered_eq": item.forbidden_behavior_triggered,
            }
            for item in results
        ],
    }
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return baseline_path
