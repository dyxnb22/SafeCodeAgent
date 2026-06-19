"""Enterprise evaluation case and result models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from safecode.enterprise.workflow.contracts import RunCosts

EvalSuite = Literal[
    "retrieval",
    "prompt_injection",
    "tool_classification",
    "pr_review",
    "remediation",
    "security_workflow",
    "smoke",
]


class CostBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_input_tokens: int = 6000
    max_output_tokens: int = 1500
    max_latency_ms: int = 30000
    max_dollars: float = 0.05


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    suite: EvalSuite
    goal: str
    input_fixture: str | None = None
    query: str | None = None
    actor_scope: list[str] = Field(default_factory=list)
    actor_tenant: str = "local"
    expected_source_ids: list[str] = Field(default_factory=list)
    forbidden_source_ids: list[str] = Field(default_factory=list)
    expected_evidence: list[str] = Field(default_factory=list)
    expected_behavior: list[str] = Field(default_factory=list)
    forbidden_behavior: list[str] = Field(default_factory=list)
    safety_assertions: list[str] = Field(default_factory=list)
    cost_budget: CostBudget = Field(default_factory=CostBudget)
    k: int = 5
    metrics: dict[str, float] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    actor: dict[str, Any] = Field(default_factory=dict)
    pass_condition: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    suite: str
    passed: bool
    expected_evidence_recall: float = 1.0
    forbidden_behavior_triggered: list[str] = Field(default_factory=list)
    safety_assertion_failures: list[str] = Field(default_factory=list)
    cost_used: RunCosts = Field(default_factory=RunCosts)
    notes: str = ""
    metrics: dict[str, float] = Field(default_factory=dict)
