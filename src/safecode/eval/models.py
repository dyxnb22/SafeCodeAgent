"""Shared data models for SafeCode eval runners."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class LiveEvalFixture:
    """One live eval task.

    ``setup_files``: dict of ``{relative_path: content}`` written into a temp project.
    ``goal``: natural-language task given to the agent.
    ``success_condition``: callable ``(project_root: Path) -> bool``.
    ``max_turns``: hard cap on agent loop iterations.
    ``category``: fixture taxonomy (bug-fix, refactor, docs-edit, config, safety, provider-robustness).
    ``expected_difficulty``: rough difficulty estimate for reporting (easy, medium, hard).
    ``fixture_stability``: stable fixtures are included in the ratchet; flaky ones are not.
    """

    name: str
    setup_files: dict[str, str]
    goal: str
    success_condition: Callable[[Path], bool]
    max_turns: int = 8
    category: str = "bug-fix"
    expected_difficulty: str = "medium"
    fixture_stability: str = "stable"
    validation_commands: list[str] = field(default_factory=list)
    max_success_condition_repairs: int = 0
    expected_relevant_files: set[str] = field(default_factory=set)
    expected_symbols: set[str] = field(default_factory=set)
    source_kind: str = "inline"
    initial_commit: str | None = None
    task_type: str = "coding"
    eval_suite: str = "auto"


@dataclass
class LiveEvalResult:
    """Metrics collected for one live fixture run."""

    fixture_name: str
    success: bool
    turns_used: int
    tool_calls: int
    redundant_reads: int
    input_tokens: int
    output_tokens: int
    wall_seconds: float
    error: str | None = None
    # Structured failure classification (mirrors FailureCategory enum values).
    failure_category: str | None = None
    # Provider / model identity for multi-model comparison.
    provider_name: str | None = None
    model_name: str | None = None
    # Observability flags surfaced from the agent runtime.
    context_fallback_used: bool = False
    patch_retry_needed: bool = False
    # Safety: no leftover .tmp / partial-patch files in the workspace after eval.
    working_tree_clean_after_eval: bool = True
    # Audit: hash-chain linkage was intact after the session.
    audit_chain_complete: bool = True
    # Approval gates: count of proposal events that required human approval.
    approval_gates_triggered: int = 0
    # Mutations: files created/modified outside the declared fixture scope.
    unauthorized_mutations: int = 0
    # Checkpoint: SHA-256 of every backup file matched the stored value.
    checkpoint_integrity_ok: bool = True
    # Provider: the LLM response was parsed without a format failure.
    provider_parse_succeeded: bool = True
    # Recovery: a malformed response was recovered via retry and the task succeeded.
    malformed_patch_recovered: bool = False
    tests_run: int = 0
    test_passed: bool = True
    validation_commands: list[str] = field(default_factory=list)
    repair_attempts: int = 0
    success_condition_retry_needed: bool = False
    success_condition_recovered: bool = False
    relevant_file_recall: float | None = None
    relevant_file_precision: float | None = None
    symbol_localization_accuracy: float | None = None
    minimal_diff_score: int | None = None
    mergeability_score: int | None = None
    reviewer_accept: bool | None = None
    source_kind: str = "inline"
    initial_commit: str | None = None
    task_type: str = "coding"
    eval_suite: str = "regression"
    transcript_path: str | None = None
    grader_results: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_name": self.fixture_name,
            "success": self.success,
            "turns_used": self.turns_used,
            "tool_calls": self.tool_calls,
            "redundant_reads": self.redundant_reads,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "wall_seconds": round(self.wall_seconds, 3),
            "error": self.error,
            "failure_category": self.failure_category,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "context_fallback_used": self.context_fallback_used,
            "patch_retry_needed": self.patch_retry_needed,
            "working_tree_clean_after_eval": self.working_tree_clean_after_eval,
            "audit_chain_complete": self.audit_chain_complete,
            "approval_gates_triggered": self.approval_gates_triggered,
            "unauthorized_mutations": self.unauthorized_mutations,
            "checkpoint_integrity_ok": self.checkpoint_integrity_ok,
            "provider_parse_succeeded": self.provider_parse_succeeded,
            "malformed_patch_recovered": self.malformed_patch_recovered,
            "tests_run": self.tests_run,
            "test_passed": self.test_passed,
            "validation_commands": list(self.validation_commands),
            "repair_attempts": self.repair_attempts,
            "success_condition_retry_needed": self.success_condition_retry_needed,
            "success_condition_recovered": self.success_condition_recovered,
            "relevant_file_recall": self.relevant_file_recall,
            "relevant_file_precision": self.relevant_file_precision,
            "symbol_localization_accuracy": self.symbol_localization_accuracy,
            "minimal_diff_score": self.minimal_diff_score,
            "mergeability_score": self.mergeability_score,
            "reviewer_accept": self.reviewer_accept,
            "source_kind": self.source_kind,
            "initial_commit": self.initial_commit,
            "task_type": self.task_type,
            "eval_suite": self.eval_suite,
            "transcript_path": self.transcript_path,
            "grader_results": list(self.grader_results),
        }


@dataclass(frozen=True)
class LiveEvalGraderResult:
    """One independent grader outcome for a live eval trial."""

    name: str
    passed: bool
    score: float
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "score": round(self.score, 3),
            "message": self.message,
        }


@dataclass
class LiveRepeatedFixtureSummary:
    """Aggregated stability metrics for one fixture across repeated runs."""

    fixture_name: str
    runs: int
    pass_rate: float
    retry_rate: float
    repair_rate: float
    recovery_rate: float
    avg_tokens: float
    p95_tokens: float
    avg_wall_seconds: float
    p95_wall_seconds: float
    safety_invariants_ok: bool
    pass_at_1: float
    pass_at_n: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_name": self.fixture_name,
            "runs": self.runs,
            "pass_rate": self.pass_rate,
            "retry_rate": self.retry_rate,
            "repair_rate": self.repair_rate,
            "recovery_rate": self.recovery_rate,
            "avg_tokens": round(self.avg_tokens, 3),
            "p95_tokens": round(self.p95_tokens, 3),
            "avg_wall_seconds": round(self.avg_wall_seconds, 3),
            "p95_wall_seconds": round(self.p95_wall_seconds, 3),
            "safety_invariants_ok": self.safety_invariants_ok,
            "pass_at_1": self.pass_at_1,
            "pass_at_n": self.pass_at_n,
        }


@dataclass
class LiveRepeatedSummary:
    """Aggregated repeated-run summary for live eval results."""

    fixtures: list[LiveRepeatedFixtureSummary]

    @property
    def overall_pass_rate(self) -> float:
        if not self.fixtures:
            return 0.0
        return round(sum(f.pass_rate for f in self.fixtures) / len(self.fixtures), 3)

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall_pass_rate": self.overall_pass_rate,
            "fixtures": [f.as_dict() for f in self.fixtures],
        }
