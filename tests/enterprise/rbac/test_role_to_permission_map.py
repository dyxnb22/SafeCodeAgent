"""Role-to-permission map tests."""

from safecode.enterprise.approvals.store import Action
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.rbac.permissions import (
    ACTION_PERMISSIONS,
    minimum_approval_role,
    rbac_tier_for_action,
    role_permission_matrix,
)
from safecode.enterprise.workflow.types import RiskTier


def test_every_action_has_permission_row():
    for action in Action:
        assert action in ACTION_PERMISSIONS


def test_viewer_cannot_write_or_approve_gate_actions():
    subject = RBACSubject(actor_id="user:viewer", roles=(Role.viewer,))
    assert rbac_tier_for_action(subject, Action.file_write) == "BLOCK"
    assert rbac_tier_for_action(subject, Action.github_read) == "AUTO"


def test_developer_blocked_on_live_github_write_comment():
    subject = RBACSubject(actor_id="user:dev", roles=(Role.developer,))
    tier = rbac_tier_for_action(
        subject,
        Action.github_write_comment,
        risk_tier=RiskTier.medium,
        context={"mode": "live"},
    )
    assert tier == "BLOCK"


def test_maintainer_can_gate_live_github_write_comment():
    subject = RBACSubject(actor_id="user:maint", roles=(Role.maintainer,))
    tier = rbac_tier_for_action(
        subject,
        Action.github_write_comment,
        risk_tier=RiskTier.high,
        context={"mode": "live"},
    )
    assert tier == "GATE"


def test_platform_admin_policy_change_requires_unlock():
    subject = RBACSubject(actor_id="user:admin", roles=(Role.platform_admin,))
    blocked = rbac_tier_for_action(subject, Action.policy_config_change)
    assert blocked == "BLOCK"
    unlocked = rbac_tier_for_action(
        subject, Action.policy_config_change, context={"org_unlock": "true"}
    )
    assert unlocked == "GATE"


def test_matrix_covers_all_roles_and_actions():
    matrix = role_permission_matrix()
    assert set(matrix) == set(Role)
    for role, actions in matrix.items():
        assert set(actions) == set(Action)


def test_minimum_approval_role_for_file_write():
    assert minimum_approval_role(Action.file_write) == Role.maintainer
