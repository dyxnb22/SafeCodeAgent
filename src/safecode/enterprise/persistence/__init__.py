"""Enterprise persistence protocols and helpers."""

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
