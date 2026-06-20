"""Enterprise tool registry and specifications.

中文包说明：企业工具注册表与规格。
- 未知工具默认拒绝；每个 ToolSpec 声明类别与审批层级。
- 工具调用须经提案 → 策略/RBAC 门控 → 人工审批（如需）→ 执行，模型输出不构成执行权威。
"""

from safecode.enterprise.tools.registry import (
    ApprovalTier,
    ToolCategory,
    ToolNotRegisteredError,
    ToolRegistry,
    ToolRegistryConflictError,
    ToolSpec,
)

__all__ = [
    "ApprovalTier",
    "ToolCategory",
    "ToolNotRegisteredError",
    "ToolRegistry",
    "ToolRegistryConflictError",
    "ToolSpec",
]
