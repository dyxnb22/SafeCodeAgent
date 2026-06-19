"""Approval tier engine."""

from __future__ import annotations

from dataclasses import dataclass

from safecode.enterprise.approvals.store import Action
from safecode.enterprise.policy.models import ApprovalTier, max_tier, normalize_policy_key
from safecode.enterprise.policy.resolver import policy_tier
from safecode.enterprise.policy.models import PolicySnapshot
from safecode.enterprise.rbac.models import RBACSubject
from safecode.enterprise.rbac.permissions import ApprovalContext, rbac_tier_for_action
from safecode.enterprise.tools.registry import ToolSpec
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.trace.session import TraceSession
from safecode.enterprise.workflow.state import ApprovalDecision, ApprovalDecisionInputs
from safecode.enterprise.workflow.types import RiskTier


@dataclass(frozen=True)
class DecisionScenario:
    action: Action
    role: str
    policy_tier: ApprovalTier
    tool_tier: ApprovalTier
    expected: ApprovalTier
    risk_tier: RiskTier = RiskTier.low
    context: ApprovalContext | None = None


DECISION_MATRIX: tuple[DecisionScenario, ...] = (
    DecisionScenario(Action.file_write, "maintainer", "GATE", "GATE", "GATE", RiskTier.high),
    DecisionScenario(Action.file_write, "developer", "GATE", "GATE", "BLOCK", RiskTier.high),
    DecisionScenario(Action.command_execute, "developer", "CONFIRM", "CONFIRM", "CONFIRM", RiskTier.low),
    DecisionScenario(Action.command_execute, "developer", "CONFIRM", "CONFIRM", "BLOCK", RiskTier.high, {"risk": "high"}),
    DecisionScenario(Action.scanner_run, "developer", "CONFIRM", "CONFIRM", "CONFIRM", RiskTier.low),
    DecisionScenario(Action.scanner_run, "developer", "CONFIRM", "CONFIRM", "BLOCK", RiskTier.medium, {"networked": "true"}),
    DecisionScenario(Action.github_read, "viewer", "AUTO", "AUTO", "AUTO"),
    DecisionScenario(Action.github_write_comment, "maintainer", "GATE", "GATE", "GATE", RiskTier.medium, {"mode": "live"}),
    DecisionScenario(Action.github_write_comment, "developer", "GATE", "GATE", "BLOCK", RiskTier.medium, {"mode": "live"}),
    DecisionScenario(Action.github_write_comment, "developer", "AUTO", "AUTO", "AUTO", RiskTier.low, {"mode": "fixture"}),
    DecisionScenario(Action.github_branch_push, "maintainer", "GATE", "GATE", "BLOCK", RiskTier.high, {"protected_branch": "true"}),
    DecisionScenario(Action.github_pr_create, "maintainer", "GATE", "GATE", "GATE", RiskTier.high),
    DecisionScenario(Action.issue_comment, "maintainer", "GATE", "GATE", "GATE", RiskTier.low, {"mode": "live"}),
    DecisionScenario(Action.mcp_read, "developer", "CONFIRM", "CONFIRM", "CONFIRM", RiskTier.low),
    DecisionScenario(Action.mcp_read, "developer", "CONFIRM", "CONFIRM", "BLOCK", RiskTier.low, {"server_known": "false"}),
    DecisionScenario(Action.mcp_write, "maintainer", "GATE", "GATE", "GATE", RiskTier.medium),
    DecisionScenario(Action.mcp_write, "maintainer", "GATE", "GATE", "BLOCK", RiskTier.high, {"server_known": "false"}),
    DecisionScenario(Action.retrieval_source_access, "viewer", "AUTO", "AUTO", "AUTO"),
    DecisionScenario(Action.retrieval_source_access, "viewer", "AUTO", "AUTO", "BLOCK", context={"scope": "denied"}),
    DecisionScenario(
        Action.memory_fact_inject,
        "security_reviewer",
        "GATE",
        "GATE",
        "GATE",
        context={"fact_status": "approved"},
    ),
    DecisionScenario(
        Action.memory_fact_inject,
        "viewer",
        "GATE",
        "GATE",
        "BLOCK",
        context={"fact_status": "pending"},
    ),
    DecisionScenario(Action.policy_config_change, "platform_admin", "GATE", "GATE", "GATE", context={"org_unlock": "true"}),
    DecisionScenario(Action.policy_config_change, "maintainer", "GATE", "GATE", "BLOCK", context={"org_unlock": "true"}),
    DecisionScenario(Action.production_access, "maintainer", "GATE", "GATE", "GATE", context={"unlock": "true"}),
    DecisionScenario(Action.production_access, "maintainer", "BLOCK", "GATE", "BLOCK"),
)


def _tool_tier_value(tool_spec: ToolSpec | ApprovalTier | None) -> ApprovalTier:
    if tool_spec is None:
        return "GATE"
    if isinstance(tool_spec, str):
        return tool_spec
    return tool_spec.approval_tier.value  # type: ignore[return-value]


def decide(
    action: Action,
    *,
    policy_snapshot: PolicySnapshot,
    subject: RBACSubject,
    tool_spec: ToolSpec | ApprovalTier | None = None,
    risk_tier: RiskTier = RiskTier.low,
    context: ApprovalContext | None = None,
) -> ApprovalDecision:
    policy_value = policy_tier(policy_snapshot, action.value)
    rbac_value = rbac_tier_for_action(subject, action, risk_tier=risk_tier, context=context)
    tool_spec_value = _tool_tier_value(tool_spec)
    decision = max_tier(policy_value, rbac_value, tool_spec_value)
    reason_parts = [
        f"policy={policy_value}",
        f"rbac={rbac_value}",
        f"tool={tool_spec_value}",
    ]
    return ApprovalDecision(
        decision=decision,
        reason=f"max strictness of {', '.join(reason_parts)}",
        policy_snapshot_id=policy_snapshot.snapshot_id,
        inputs=ApprovalDecisionInputs(
            policy_value=policy_value,
            rbac_value=rbac_value,
            tool_spec_value=tool_spec_value,
        ),
    )


def trace_decision(
    session: TraceSession,
    *,
    action: Action,
    decision: ApprovalDecision,
    node_id: str = "approval_engine",
) -> None:
    """Record an approval-engine evaluation in the run trace."""
    event_type = (
        TraceEventType.policy_block
        if decision.decision == "BLOCK"
        else TraceEventType.approval_decided
    )
    session.emit(
        event_type,
        node_id=node_id,
        payload={
            "action": action.value,
            "decision": decision.decision,
            "reason": decision.reason,
        },
        audit=False,
    )


def decide_with_trace(
    session: TraceSession,
    action: Action,
    *,
    policy_snapshot: PolicySnapshot,
    subject: RBACSubject,
    tool_spec: ToolSpec | ApprovalTier | None = None,
    risk_tier: RiskTier = RiskTier.low,
    context: ApprovalContext | None = None,
) -> ApprovalDecision:
    decision = decide(
        action,
        policy_snapshot=policy_snapshot,
        subject=subject,
        tool_spec=tool_spec,
        risk_tier=risk_tier,
        context=context,
    )
    trace_decision(session, action=action, decision=decision)
    return decision


def decide_with_overrides(
    action: Action,
    *,
    policy_snapshot: PolicySnapshot,
    subject: RBACSubject,
    policy_override: ApprovalTier | None = None,
    rbac_override: ApprovalTier | None = None,
    tool_override: ApprovalTier | None = None,
    risk_tier: RiskTier = RiskTier.low,
    context: ApprovalContext | None = None,
) -> ApprovalDecision:
    policy_value = policy_override or policy_tier(policy_snapshot, normalize_policy_key(action.value))
    rbac_value = rbac_override or rbac_tier_for_action(subject, action, risk_tier=risk_tier, context=context)
    tool_spec_value = tool_override or "GATE"
    decision = max_tier(policy_value, rbac_value, tool_spec_value)
    return ApprovalDecision(
        decision=decision,
        reason="max strictness of policy, rbac, and tool spec",
        policy_snapshot_id=policy_snapshot.snapshot_id,
        inputs=ApprovalDecisionInputs(
            policy_value=policy_value,
            rbac_value=rbac_value,
            tool_spec_value=tool_spec_value,
        ),
    )
