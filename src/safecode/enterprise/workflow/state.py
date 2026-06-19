"""Enterprise workflow run state models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from safecode.enterprise.rag.models import Citation
from safecode.enterprise.connectors.models import IssueEvidence, PullRequestEvidence
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.workflow.contracts import NodeCost, NodeOutput, RunCosts
from safecode.enterprise.workflow.exceptions import InvalidStateSchemaVersionError
from safecode.enterprise.workflow.types import RiskTier, TaskType, WorkflowStatus

STATE_SCHEMA_VERSION = "1.2.0"
SUPPORTED_STATE_SCHEMA_VERSIONS = frozenset({STATE_SCHEMA_VERSION})


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: TaskType
    input_kind: Literal[
        "pr_fixture",
        "pr_live",
        "finding_fixture",
        "finding_live",
        "ticket",
        "repo_query",
    ]
    input_ref: str
    actor_id: str
    extra: dict[str, str] = Field(default_factory=dict)


class RepoContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_root: str
    branch: str = "main"
    commit_sha: str = "0000000"
    git_remote: str | None = None
    protected_branches: list[str] = Field(default_factory=lambda: ["main", "master"])


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    start_line: int
    end_line: int
    snippet_hash: str


class SecurityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    source: Literal["semgrep", "pip_audit", "sarif", "agent_analysis", "manual"]
    rule_id: str
    severity: RiskTier
    title: str
    description: str
    cwe: str | None = None
    cve: str | None = None
    location: Location


class PlanAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    title: str
    risk_tier: RiskTier
    requires_approval: bool = False


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    summary: str
    actions: list[PlanAction] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    revisit_trigger: str = ""
    citation_ids: list[str] = Field(default_factory=list)


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    kind: Literal["report", "patch", "comment", "ticket"]
    summary: str
    ref: str


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    summary: str
    details: dict[str, str] = Field(default_factory=dict)


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str
    kind: Literal["pr_review_report", "remediation_report", "plan_report", "compliance_report"]
    markdown: str


class ApprovalDecisionInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_value: Literal["AUTO", "CONFIRM", "GATE", "BLOCK"] = "GATE"
    rbac_value: Literal["AUTO", "CONFIRM", "GATE", "BLOCK"] = "GATE"
    tool_spec_value: Literal["AUTO", "CONFIRM", "GATE", "BLOCK"] = "GATE"


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["AUTO", "CONFIRM", "GATE", "BLOCK"]
    reason: str
    policy_snapshot_id: str
    inputs: ApprovalDecisionInputs = Field(default_factory=ApprovalDecisionInputs)


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    decision: ApprovalDecision
    request_status: Literal["pending", "approved", "rejected", "evidence_requested", "revoked"]
    grant_id: str | None = None
    grant_consumed_at: str | None = None


class ToolCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    run_id: str
    node_name: str
    tool_name: str
    tool_category: Literal[
        "read_local",
        "write_local",
        "command",
        "read_network",
        "write_network",
        "admin",
    ]
    inputs_redacted: dict[str, str] = Field(default_factory=dict)
    decision: ApprovalDecision
    grant_id: str | None = None
    outcome: Literal["ok", "blocked", "error", "redacted_oversize"] = "ok"
    output_excerpt: str = ""
    cost: NodeCost = Field(default_factory=NodeCost)
    started_at: str = ""
    ended_at: str = ""


class FailureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_id: str
    category: Literal[
        "model_validation",
        "retrieval_empty",
        "tool_blocked",
        "tool_error",
        "validation_failed",
        "approval_rejected",
        "policy_block",
        "sandbox_refused",
        "timeout",
        "unknown",
    ]
    node_name: str
    message: str
    retry_count: int = 0
    recoverable: bool = False


class EnterpriseRunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = STATE_SCHEMA_VERSION
    run_id: str
    tenant_id: str = "local"
    task_type: TaskType
    status: WorkflowStatus
    actor_id: str
    subject: RBACSubject
    policy_snapshot_id: str
    request: RunRequest
    repo: RepoContext
    pull_request_evidence: PullRequestEvidence | None = None
    issue_evidence: IssueEvidence | None = None
    citations: list[Citation] = Field(default_factory=list)
    findings: list[SecurityFinding] = Field(default_factory=list)
    risk_tier: RiskTier | None = None
    plan: Plan | None = None
    proposals: list[Proposal] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    validation: ValidationResult | None = None
    report: Report | None = None
    costs: RunCosts = Field(default_factory=RunCosts)
    failures: list[FailureRecord] = Field(default_factory=list)
    node_outputs: dict[str, NodeOutput] = Field(default_factory=dict)
    audit_anchor_id: str | None = None
    created_at: str
    updated_at: str
    missing_evidence: bool = False
    validation_failed: bool = False
    awaiting_human_approval: bool = False

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value not in SUPPORTED_STATE_SCHEMA_VERSIONS:
            raise InvalidStateSchemaVersionError(
                f"unsupported schema_version {value!r}; expected one of "
                f"{sorted(SUPPORTED_STATE_SCHEMA_VERSIONS)}"
            )
        return value

    def model_dump_json(self, **kwargs: Any) -> str:
        kwargs.setdefault("indent", 2)
        return super().model_dump_json(**kwargs)
