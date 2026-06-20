"""Enterprise audit taxonomy and hash-chain integration.

中文包说明：企业审计事件分类与哈希链集成。
- 记录工作流、检索、模型调用、工具提案/阻断/执行、审批全生命周期及策略阻断事件。
- 模型调用仅记观测事件，不代表执行授权；审批消费须可追溯到具体 request/grant。
- 审计链用于合规证据与事后追溯，不替代实时策略门控。
"""

from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.events import ALL_AUDIT_EVENT_KINDS, AuditEventKind, audit_kind_values

__all__ = [
    "ALL_AUDIT_EVENT_KINDS",
    "AuditEventKind",
    "EnterpriseAuditChain",
    "audit_kind_values",
]
