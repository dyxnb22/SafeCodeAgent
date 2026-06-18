"""Approval engine RBAC interaction tests."""

from pathlib import Path

from safecode.enterprise.approvals.engine import decide
from safecode.enterprise.approvals.store import Action
from safecode.enterprise.policy.resolver import resolve_policy
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.tools.registry import ApprovalTier, ToolSpec, ToolCategory
from safecode.enterprise.workflow.types import RiskTier


def test_developer_blocked_on_live_pr_comment(tmp_path: Path):
    snapshot = resolve_policy(tmp_path)
    subject = RBACSubject(actor_id="user:dev", roles=(Role.developer,))
    tool = ToolSpec(
        name="github_write",
        description="write",
        category=ToolCategory.write_network,
        approval_tier=ApprovalTier.GATE,
        action=Action.github_write_comment,
    )
    decision = decide(
        Action.github_write_comment,
        policy_snapshot=snapshot,
        subject=subject,
        tool_spec=tool,
        risk_tier=RiskTier.medium,
        context={"mode": "live"},
    )
    assert decision.decision == "BLOCK"
    assert decision.inputs.rbac_value == "BLOCK"


def test_maintainer_gets_gate_for_live_pr_comment(tmp_path: Path):
    snapshot = resolve_policy(tmp_path)
    subject = RBACSubject(actor_id="user:maint", roles=(Role.maintainer,))
    tool = ToolSpec(
        name="github_write",
        description="write",
        category=ToolCategory.write_network,
        approval_tier=ApprovalTier.GATE,
        action=Action.github_write_comment,
    )
    decision = decide(
        Action.github_write_comment,
        policy_snapshot=snapshot,
        subject=subject,
        tool_spec=tool,
        risk_tier=RiskTier.high,
        context={"mode": "live"},
    )
    assert decision.decision == "GATE"
    assert decision.inputs.rbac_value == "GATE"
