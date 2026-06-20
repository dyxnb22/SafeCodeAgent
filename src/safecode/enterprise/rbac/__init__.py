"""Enterprise RBAC models and permission helpers.

中文包说明：基于角色的访问控制（RBAC）。
- 将主体（RBACSubject）映射到角色与权限范围，为策略解析与审批决策提供上下文。
- RBAC 裁决与策略层（PolicySnapshot）叠加：二者取更严格结果，不得单独放宽门控。
- --as-role 模拟须受组织策略 allow_as_role_flag 约束，默认拒绝。
"""

from safecode.enterprise.rbac.models import (
    DEFAULT_SCOPES_BY_ROLE,
    ROLE_RANK,
    RBACSubject,
    Role,
    load_user_role_from_file,
    resolve_subject,
)
from safecode.enterprise.rbac.permissions import (
    ACTION_PERMISSIONS,
    can_approve_action,
    minimum_approval_role,
    rbac_tier_for_action,
    role_permission_matrix,
)

__all__ = [
    "ACTION_PERMISSIONS",
    "DEFAULT_SCOPES_BY_ROLE",
    "ROLE_RANK",
    "RBACSubject",
    "Role",
    "can_approve_action",
    "load_user_role_from_file",
    "minimum_approval_role",
    "rbac_tier_for_action",
    "resolve_subject",
    "role_permission_matrix",
]
