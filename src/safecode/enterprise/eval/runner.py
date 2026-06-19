"""Enterprise evaluation runner."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from safecode.enterprise.eval.cases import EvaluationCase, EvaluationResult
from safecode.enterprise.eval.assertions import evaluate_safety_assertions
from safecode.enterprise.eval.loader import discover_cases, load_case_file
from safecode.enterprise.eval.prompt_injection import run_prompt_injection_evaluation
from safecode.enterprise.eval.pr_review import run_pr_review_evaluation
from safecode.enterprise.eval.remediation import run_remediation_evaluation
from safecode.enterprise.eval.retrieval import run_retrieval_evaluation
from safecode.enterprise.eval.tool_classification import run_tool_classification_evaluation
from safecode.enterprise.trace.redaction import DEFAULT_TRACE_EXPORT_PROFILE
from safecode.enterprise.workflow.contracts import NodeCost, RunCosts

STRICT_TRACE_PROFILE = DEFAULT_TRACE_EXPORT_PROFILE


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _mock_costs() -> RunCosts:
    now = _utc_now()
    total = NodeCost(input_tokens=0, output_tokens=0, latency_ms=1, provider="mock", request_count=1)
    return RunCosts(by_node={"smoke": total}, total=total, dollars_estimate=0.0, started_at=now, ended_at=now)


def run_smoke_case(case: EvaluationCase) -> EvaluationResult:
    started = time.monotonic()
    safety_failures = evaluate_safety_assertions(
        case.safety_assertions,
        facts={"audit_chain_intact": True, "no_unauthorized_mutation": True},
    )
    passed = case.suite == "smoke" and not safety_failures
    elapsed_ms = int((time.monotonic() - started) * 1000)
    costs = _mock_costs()
    costs.total.latency_ms = elapsed_ms
    return EvaluationResult(
        case_id=case.case_id,
        suite=case.suite,
        passed=passed,
        expected_evidence_recall=1.0 if passed else 0.0,
        cost_used=costs,
        notes="smoke pass-through",
        safety_assertion_failures=safety_failures,
    )


def run_case(
    case: EvaluationCase,
    *,
    project_root: Path,
    manifest_path: Path | None = None,
) -> EvaluationResult:
    _ = project_root
    _ = manifest_path
    os.environ.setdefault("EVAL_TRACE_PROFILE", STRICT_TRACE_PROFILE)
    if case.suite == "smoke":
        return run_smoke_case(case)
    if case.suite == "retrieval":
        if manifest_path is None:
            return EvaluationResult(
                case_id=case.case_id,
                suite=case.suite,
                passed=False,
                notes="retrieval suite requires manifest_path",
            )
        return run_retrieval_evaluation(case, manifest_path, project_root)
    if case.suite == "prompt_injection":
        return run_prompt_injection_evaluation(case, project_root)
    if case.suite == "tool_classification":
        return run_tool_classification_evaluation(case, project_root)
    if case.suite == "pr_review":
        return run_pr_review_evaluation(case, project_root)
    if case.suite == "remediation":
        return run_remediation_evaluation(case, project_root)
    return EvaluationResult(
        case_id=case.case_id,
        suite=case.suite,
        passed=False,
        notes=f"runner does not yet execute suite {case.suite}",
    )


def run_suite(
    cases: list[EvaluationCase],
    *,
    project_root: Path,
    manifest_path: Path | None = None,
) -> list[EvaluationResult]:
    return [run_case(case, project_root=project_root, manifest_path=manifest_path) for case in cases]


def write_results(results: list[EvaluationResult], sac_root: Path, run_id: str) -> Path:
    directory = sac_root / "enterprise" / "eval" / "results" / run_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "results.json"
    payload = [json.loads(item.model_dump_json()) for item in results]
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    return path


__all__ = [
    "discover_cases",
    "load_case_file",
    "run_case",
    "run_suite",
    "run_smoke_case",
    "write_results",
]
