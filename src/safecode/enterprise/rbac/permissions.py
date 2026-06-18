"""Role-to-action permission map for enterprise governance."""

from __future__ import annotations

from dataclasses import dataclass

from safecode.enterprise.approvals.store import Action
from safecode.enterprise.policy.models import ApprovalTier
from safecode.enterprise.rbac.models import ROLE_RANK, Role, RBACSubject
from safecode.enterprise.workflow.types import RiskTier

ApprovalContext = dict[str, str]


@dataclass(frozen=True)
class ActionPermission:
    action: Action
    minimum_role: Role
    approve_role: Role | None
    default_rbac_tier: ApprovalTier = "AUTO"


ACTION_PERMISSIONS: dict[Action, ActionPermission] = {
    Action.file_write: ActionPermission(Action.file_write, Role.maintainer, Role.maintainer, "GATE"),
    Action.command_execute: ActionPermission(Action.command_execute, Role.developer, Role.developer, "CONFIRM"),
    Action.scanner_run: ActionPermission(Action.scanner_run, Role.developer, Role.developer, "CONFIRM"),
    Action.github_read: ActionPermission(Action.github_read, Role.viewer, None, "AUTO"),
    Action.github_write_comment: ActionPermission(
        Action.github_write_comment, Role.maintainer, Role.maintainer, "GATE"
    ),
    Action.github_branch_push: ActionPermission(
        Action.github_branch_push, Role.maintainer, Role.maintainer, "GATE"
    ),
    Action.github_pr_create: ActionPermission(Action.github_pr_create, Role.maintainer, Role.maintainer, "GATE"),
    Action.issue_comment: ActionPermission(Action.issue_comment, Role.maintainer, Role.maintainer, "GATE"),
    Action.mcp_read: ActionPermission(Action.mcp_read, Role.developer, Role.developer, "CONFIRM"),
    Action.mcp_write: ActionPermission(Action.mcp_write, Role.maintainer, Role.maintainer, "GATE"),
    Action.retrieval_source_access: ActionPermission(
        Action.retrieval_source_access, Role.viewer, None, "AUTO"
    ),
    Action.memory_fact_inject: ActionPermission(Action.memory_fact_inject, Role.viewer, None, "AUTO"),
    Action.policy_config_change: ActionPermission(
        Action.policy_config_change, Role.platform_admin, Role.platform_admin, "BLOCK"
    ),
    Action.production_access: ActionPermission(
        Action.production_access, Role.maintainer, Role.maintainer, "BLOCK"
    ),
}


def _role_at_least(subject: RBACSubject, minimum: Role) -> bool:
    return ROLE_RANK[subject.highest_role()] >= ROLE_RANK[minimum]


def _risk_value(tier: RiskTier) -> int:
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}[tier.value]


def rbac_tier_for_action(
    subject: RBACSubject,
    action: Action,
    *,
    risk_tier: RiskTier = RiskTier.low,
    context: ApprovalContext | None = None,
) -> ApprovalTier:
    ctx = dict(context or {})
    permission = ACTION_PERMISSIONS[action]

    if action == Action.retrieval_source_access and ctx.get("scope") == "denied":
        return "BLOCK"
    if action == Action.memory_fact_inject and ctx.get("fact_status") == "pending":
        return "BLOCK"
    if action == Action.mcp_read and ctx.get("server_known") == "false":
        return "BLOCK"
    if action == Action.mcp_write and ctx.get("server_known") == "false":
        return "BLOCK"
    if action == Action.mcp_write and ctx.get("risk") == "high":
        return "BLOCK"
    if action == Action.github_branch_push and ctx.get("protected_branch") == "true":
        return "BLOCK"
    if action == Action.github_pr_create and ctx.get("protected_branch") == "true":
        return "BLOCK"
    if action == Action.command_execute and ctx.get("risk") == "high":
        if not _role_at_least(subject, Role.maintainer):
            return "BLOCK"
        return "GATE"
    if action == Action.scanner_run and ctx.get("networked") == "true":
        if not _role_at_least(subject, Role.maintainer):
            return "BLOCK"
        return "GATE"
    if action == Action.github_write_comment and ctx.get("mode") == "fixture":
        return "AUTO"
    if action == Action.issue_comment and ctx.get("mode") == "fixture":
        return "AUTO"
    if action == Action.github_write_comment and ctx.get("mode") == "live":
        if not _role_at_least(subject, Role.maintainer):
            return "BLOCK"
        return "GATE"
    if action == Action.issue_comment and ctx.get("mode") == "live":
        if not _role_at_least(subject, Role.maintainer):
            return "BLOCK"
        return "GATE"
    if action == Action.policy_config_change:
        if not _role_at_least(subject, Role.platform_admin):
            return "BLOCK"
        if ctx.get("org_unlock") != "true":
            return "BLOCK"
        return "GATE"
    if action == Action.production_access:
        if ctx.get("unlock") != "true":
            return "BLOCK"
        if not _role_at_least(subject, Role.maintainer):
            return "BLOCK"
        return "GATE"

    if not _role_at_least(subject, permission.minimum_role):
        return "BLOCK"

    role = subject.highest_role()
    if permission.approve_role is None:
        return permission.default_rbac_tier

    if role == Role.viewer:
        return "BLOCK"
    if role == Role.developer:
        if permission.default_rbac_tier in {"AUTO", "CONFIRM"}:
            return permission.default_rbac_tier
        return "BLOCK"
    if role == Role.security_reviewer:
        if permission.default_rbac_tier in {"AUTO", "CONFIRM"}:
            return permission.default_rbac_tier
        if permission.default_rbac_tier == "GATE" and _risk_value(risk_tier) <= _risk_value(RiskTier.medium):
            return "GATE"
        return "BLOCK"
    return permission.default_rbac_tier


def can_approve_action(
    subject: RBACSubject,
    action: Action,
    *,
    risk_tier: RiskTier = RiskTier.low,
    context: ApprovalContext | None = None,
) -> bool:
    tier = rbac_tier_for_action(subject, action, risk_tier=risk_tier, context=context)
    return tier != "BLOCK"


def role_permission_matrix() -> dict[Role, dict[Action, ApprovalTier]]:
    matrix: dict[Role, dict[Action, ApprovalTier]] = {}
    for role in Role:
        subject = RBACSubject(actor_id=f"user:{role.value}", roles=(role,))
        matrix[role] = {
            action: rbac_tier_for_action(subject, action, risk_tier=RiskTier.medium)
            for action in Action
        }
    return matrix


def minimum_approval_role(action: Action) -> Role | None:
    return ACTION_PERMISSIONS[action].approve_role
