"""Evaluation case schema tests."""

from pathlib import Path

import yaml

from safecode.enterprise.eval.cases import CostBudget, EvaluationCase, EvaluationResult


def test_evaluation_case_defaults_match_data_models():
    case = EvaluationCase(
        case_id="smoke.pass_through",
        suite="smoke",
        goal="Trivial pass-through validation.",
    )
    assert case.cost_budget.max_input_tokens == 6000
    assert case.cost_budget.max_latency_ms == 30000
    assert case.actor_tenant == "local"


def test_evaluation_case_loads_from_yaml_dict():
    raw = {
        "case_id": "retrieval.policy.sql_injection",
        "suite": "retrieval",
        "goal": "Retrieve SQL policy",
        "query": "sql injection parameterized",
        "actor_scope": ["org"],
        "expected_source_ids": ["policy-secure-sql-001"],
        "metrics": {"recall_at_k": 1.0},
    }
    case = EvaluationCase.model_validate(raw)
    assert case.suite == "retrieval"
    assert case.metrics["recall_at_k"] == 1.0


def test_evaluation_result_shape():
    result = EvaluationResult(
        case_id="smoke.pass_through",
        suite="smoke",
        passed=True,
        expected_evidence_recall=1.0,
        notes="ok",
    )
    assert result.forbidden_behavior_triggered == []
    assert result.safety_assertion_failures == []


def test_existing_retrieval_yaml_parses(tmp_path: Path):
    case_path = (
        Path(__file__).resolve().parent / "cases" / "retrieval" / "sql_injection.yaml"
    )
    raw = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    case = EvaluationCase.model_validate(raw)
    assert case.case_id == "retrieval.policy.sql_injection"
    assert isinstance(case.cost_budget, CostBudget)
