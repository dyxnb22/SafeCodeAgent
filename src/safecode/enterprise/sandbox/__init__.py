"""Enterprise sandbox helpers.

中文包说明：企业沙箱与 PR 工作区辅助。
- 沙箱提案与执行分阶段记录；实际变更须经审批与回滚保障。
- 沙箱内操作仍受策略门控，不得因隔离而放宽权限。
"""

from safecode.enterprise.sandbox.pr_workspace import (
    PRWorkspaceCheckout,
    PRWorkspaceCleanupOutcome,
    PRWorkspaceError,
    PRWorkspaceManager,
    PRWorkspaceMutationError,
    PRWorkspaceSecurityError,
    PRWorkspaceSpec,
)

__all__ = [
    "PRWorkspaceCheckout",
    "PRWorkspaceCleanupOutcome",
    "PRWorkspaceError",
    "PRWorkspaceManager",
    "PRWorkspaceMutationError",
    "PRWorkspaceSecurityError",
    "PRWorkspaceSpec",
]
