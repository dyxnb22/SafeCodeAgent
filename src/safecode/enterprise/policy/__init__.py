"""Enterprise policy precedence and snapshots.

中文包说明：企业策略解析与快照。
- 多层策略（workflow → env → project → user → org）按优先级合并，低层不得弱化高层约束。
- 被阻断的弱化尝试记录在 blocked_overrides，供审计与排障。
- 项目本地配置不能削弱用户级或组织级策略；策略快照 ID 须与审批绑定一致。
"""

from safecode.enterprise.policy.models import (
    ApprovalTier,
    PolicyLayer,
    PolicyOverrideBlocked,
    PolicySnapshot,
    PolicyValue,
    max_tier,
    normalize_policy_key,
)
from safecode.enterprise.policy.resolver import (
    PolicyResolver,
    policy_bool,
    policy_tier,
    resolve_policy,
)

__all__ = [
    "ApprovalTier",
    "PolicyLayer",
    "PolicyOverrideBlocked",
    "PolicyResolver",
    "PolicySnapshot",
    "PolicyValue",
    "max_tier",
    "normalize_policy_key",
    "policy_bool",
    "policy_tier",
    "resolve_policy",
]
