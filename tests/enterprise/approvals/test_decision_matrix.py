"""Approval engine decision matrix tests."""

from pathlib import Path

from safecode.enterprise.approvals.engine import DECISION_MATRIX, decide_with_overrides
from safecode.enterprise.policy.resolver import resolve_policy
from safecode.enterprise.rbac.models import RBACSubject, Role


def test_decision_matrix_rows(tmp_path: Path):
    snapshot = resolve_policy(tmp_path)
    for scenario in DECISION_MATRIX:
        subject = RBACSubject(actor_id=f"user:{scenario.role}", roles=(Role(scenario.role),))
        decision = decide_with_overrides(
            scenario.action,
            policy_snapshot=snapshot,
            subject=subject,
            policy_override=scenario.policy_tier,
            rbac_override=None,
            tool_override=scenario.tool_tier,
            risk_tier=scenario.risk_tier,
            context=scenario.context,
        )
        assert decision.decision == scenario.expected, (
            f"{scenario.action.value}/{scenario.role} expected {scenario.expected}, "
            f"got {decision.decision} ({decision.reason})"
        )
        assert decision.policy_snapshot_id == snapshot.snapshot_id


def test_engine_never_relaxes_below_max_strictness(tmp_path: Path):
    snapshot = resolve_policy(tmp_path)
    subject = RBACSubject(actor_id="user:maintainer", roles=(Role.maintainer,))
    decision = decide_with_overrides(
        DECISION_MATRIX[0].action,
        policy_snapshot=snapshot,
        subject=subject,
        policy_override="AUTO",
        rbac_override="CONFIRM",
        tool_override="GATE",
    )
    assert decision.decision == "GATE"
    assert decision.inputs.policy_value == "AUTO"
    assert decision.inputs.rbac_value == "CONFIRM"
    assert decision.inputs.tool_spec_value == "GATE"
