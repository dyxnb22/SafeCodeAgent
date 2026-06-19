"""Repository protocol definitions for Enterprise persistence (v2.1.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from safecode.audit.models import AuditEvent
from safecode.enterprise.approvals.store import (
    Action,
    ApprovalRequest,
    Grant,
)
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.eval.cases import EvaluationResult
from safecode.enterprise.persistence.exceptions import MissingTenantIdError, TenantBoundaryError
from safecode.enterprise.trace.events import TraceEvent, TraceEventType
from safecode.enterprise.workflow.checkpoint import RunCheckpoint
from safecode.enterprise.workflow.contracts import NodeCost


def validate_tenant_id(tenant_id: str | None) -> str:
    """Require a non-empty tenant identifier for every persistence operation."""
    if tenant_id is None:
        raise MissingTenantIdError("tenant_id is required")
    normalized = tenant_id.strip()
    if not normalized:
        raise MissingTenantIdError("tenant_id is required")
    return normalized


def assert_tenant_match(expected: str, actual: str, *, operation: str) -> None:
    """Fail closed when persisted tenant scope does not match the caller."""
    if validate_tenant_id(expected) != validate_tenant_id(actual):
        raise TenantBoundaryError(f"{operation} tenant mismatch")


ApprovalDecision = Literal["approved", "rejected", "evidence_requested", "revoked"]


@runtime_checkable
class RunStore(Protocol):
    """Run checkpoint persistence."""

    def save_checkpoint(self, *, tenant_id: str, checkpoint: RunCheckpoint) -> None: ...

    def load_checkpoint(self, *, tenant_id: str, run_id: str) -> RunCheckpoint: ...

    def resolve_run_tenant(self, *, run_id: str) -> str: ...

    def purge_run(self, *, tenant_id: str, run_id: str) -> None: ...

    def gc_runs(self, *, tenant_id: str, older_than_days: int) -> list[str]: ...


@runtime_checkable
class ApprovalStore(Protocol):
    """Approval request and grant persistence."""

    def save_request(self, *, tenant_id: str, request: ApprovalRequest) -> ApprovalRequest: ...

    def load_request(
        self, *, tenant_id: str, run_id: str, request_id: str
    ) -> ApprovalRequest: ...

    def list_requests(self, *, tenant_id: str, run_id: str) -> list[ApprovalRequest]: ...

    def list_pending_requests(self, *, tenant_id: str, run_id: str) -> list[ApprovalRequest]: ...

    def decide_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision: ApprovalDecision,
        decision_actor: str,
        decision_note: str = "",
    ) -> ApprovalRequest: ...

    def request_evidence(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision_actor: str,
        decision_note: str,
    ) -> ApprovalRequest: ...

    def revoke_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision_actor: str,
        decision_note: str = "",
    ) -> ApprovalRequest: ...

    def save_grant(self, *, tenant_id: str, grant: Grant) -> Grant: ...

    def load_grant(self, *, tenant_id: str, run_id: str, grant_id: str) -> Grant: ...

    def consume_grant(self, *, tenant_id: str, run_id: str, grant_id: str) -> Grant: ...

    def validate_approved_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        action: Action,
        policy_snapshot_id: str,
        target: dict[str, str],
    ) -> tuple[ApprovalRequest, Grant]: ...

    def consume_approved_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        action: Action,
        policy_snapshot_id: str,
        target: dict[str, str],
    ) -> Grant: ...


@runtime_checkable
class AuditStore(Protocol):
    """Append-only audit hash-chain persistence."""

    def emit(
        self,
        kind: AuditEventKind,
        *,
        tenant_id: str,
        run_id: str,
        actor_id: str,
        payload: dict[str, str] | None = None,
        status: str = "success",
        message: str | None = None,
    ) -> AuditEvent: ...

    def verify_integrity(self) -> tuple[bool, str]: ...

    def list_events(self, *, tenant_id: str, run_id: str | None = None) -> list[AuditEvent]: ...


@runtime_checkable
class EvidenceStore(Protocol):
    """Evidence bundle export persistence."""

    def export_run_evidence(self, *, tenant_id: str, run_id: str) -> Path: ...


@runtime_checkable
class EvalResultStore(Protocol):
    """Evaluation result persistence."""

    def write_results(
        self, *, tenant_id: str, run_id: str, results: list[EvaluationResult]
    ) -> Path: ...

    def read_results(self, *, tenant_id: str, run_id: str) -> list[EvaluationResult]: ...


@runtime_checkable
class TraceStore(Protocol):
    """Run trace and timeline persistence."""

    def emit_event(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_type: TraceEventType | str,
        node_id: str,
        seq: int,
        payload: dict[str, object] | None = None,
        actor_id: str | None = None,
        policy_snapshot_id: str | None = None,
        cost: NodeCost | None = None,
        duration_ms: int | None = None,
        event_id: str | None = None,
        timestamp: str | None = None,
    ) -> TraceEvent | None: ...

    def list_events(self, *, tenant_id: str, run_id: str) -> list[TraceEvent]: ...

    def write_timeline(self, *, tenant_id: str, run_id: str) -> Path: ...
