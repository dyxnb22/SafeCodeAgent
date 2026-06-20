"""Enterprise persistence protocols and helpers.

中文说明
--------
持久化抽象层：定义 ``RunStore``、``ApprovalStore``、``AuditStore`` 等协议，
并提供 ``LocalBackend``（文件系统）与 ``StrictFakeBackend``（测试用）实现。
所有读写操作强制 ``tenant_id`` 校验（``assert_tenant_match``），防止跨租户泄漏。

注意：本模块重复导入了 ``LocalBackend``（第 9 行与第 21 行），属冗余而非功能差异。
"""

from safecode.enterprise.persistence.exceptions import (
    MissingTenantIdError,
    PersistenceError,
    TenantBoundaryError,
)
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.persistence.protocols import (
    ApprovalDecision,
    ApprovalStore,
    AuditStore,
    EvalResultStore,
    EvidenceStore,
    RunStore,
    TraceStore,
    assert_tenant_match,
    validate_tenant_id,
)

from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.persistence.strict_fake import StrictFakeBackend

__all__ = [
    "ApprovalDecision",
    "ApprovalStore",
    "AuditStore",
    "EvalResultStore",
    "EvidenceStore",
    "LocalBackend",
    "StrictFakeBackend",
    "MissingTenantIdError",
    "PersistenceError",
    "RunStore",
    "TenantBoundaryError",
    "TraceStore",
    "assert_tenant_match",
    "validate_tenant_id",
]
