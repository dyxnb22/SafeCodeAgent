"""Scanner finding models.

中文包说明：安全扫描器发现项模型。
- 扫描结果作为不可信输入进入工作流与 RAG，须经结构化解析与权限过滤。
- 触发 scanner_run 动作时受策略与 RBAC 门控。
"""

from safecode.enterprise.workflow.state import Location, SecurityFinding

__all__ = ["Location", "SecurityFinding"]
