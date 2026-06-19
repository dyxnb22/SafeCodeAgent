"""Strict in-memory persistence fake for protocol contract tests (v2.1.3)."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

from safecode.audit.models import AuditEvent
from safecode.enterprise.approvals.store import (
    Action,
    ApprovalRequest,
    Grant,
    GrantAlreadyConsumedError,
    grant_hash,
    grant_id_for_request,
    request_hash,
    validate_grant_id,
    validate_request_id,
)
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.eval.cases import EvaluationResult
from safecode.enterprise.persistence.local_backend import (
    LocalAuditStore,
    LocalEvalResultStore,
    LocalEvidenceStore,
    LocalTraceStore,
)
from safecode.enterprise.persistence.protocols import (
    ApprovalDecision,
    assert_tenant_match,
    validate_tenant_id,
)
from safecode.enterprise.trace.events import TraceEvent, TraceEventType
from safecode.enterprise.workflow.checkpoint import RunCheckpoint
from safecode.enterprise.workflow.contracts import NodeCost
from safecode.enterprise.workflow.exceptions import (
    ApprovalRequestExistsError,
    ApprovalRequestNotFoundError,
    ApprovalRequestTamperedError,
    CheckpointCorruptedError,
    RequestAlreadyConsumedError,
)
from safecode.enterprise.workflow.ids import validate_run_id


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class StrictFakeRunStore:
    def __init__(self) -> None:
        self._checkpoints: dict[tuple[str, str], RunCheckpoint] = {}

    def save_checkpoint(self, *, tenant_id: str, checkpoint: RunCheckpoint) -> None:
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, checkpoint.state.tenant_id, operation="save_checkpoint")
        self._checkpoints[(tenant, checkpoint.run_id)] = copy.deepcopy(checkpoint)

    def load_checkpoint(self, *, tenant_id: str, run_id: str) -> RunCheckpoint:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        checkpoint = self._checkpoints.get((tenant, run_id))
        if checkpoint is None:
            for (stored_tenant, stored_run), stored in self._checkpoints.items():
                if stored_run == run_id:
                    assert_tenant_match(tenant, stored_tenant, operation="load_checkpoint")
                    checkpoint = stored
                    break
        if checkpoint is None:
            raise CheckpointCorruptedError(f"missing checkpoint for run {run_id!r}")
        assert_tenant_match(tenant, checkpoint.state.tenant_id, operation="load_checkpoint")
        return copy.deepcopy(checkpoint)

    def resolve_run_tenant(self, *, run_id: str) -> str:
        validate_run_id(run_id)
        tenants = {tenant for tenant, stored_run_id in self._checkpoints if stored_run_id == run_id}
        if len(tenants) != 1:
            raise CheckpointCorruptedError(
                f"cannot resolve unique tenant for run {run_id!r}; found {len(tenants)}"
            )
        return validate_tenant_id(next(iter(tenants)))

    def purge_run(self, *, tenant_id: str, run_id: str) -> None:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        if (tenant, run_id) in self._checkpoints:
            self._checkpoints.pop((tenant, run_id))

    def gc_runs(self, *, tenant_id: str, older_than_days: int) -> list[str]:
        validate_tenant_id(tenant_id)
        if older_than_days < 1:
            raise ValueError("older_than_days must be at least 1")
        return []


class StrictFakeApprovalStore:
    def __init__(self) -> None:
        self._requests: dict[tuple[str, str, str], ApprovalRequest] = {}
        self._grants: dict[tuple[str, str, str], Grant] = {}

    def save_request(self, *, tenant_id: str, request: ApprovalRequest) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, request.tenant_id, operation="save_request")
        validate_request_id(request.request_id)
        key = (tenant, request.run_id, request.request_id)
        if key in self._requests:
            raise ApprovalRequestExistsError(f"approval request exists: {request.request_id}")
        stored = request.model_copy(update={"request_hash": request_hash(request)})
        self._requests[key] = stored
        return stored

    def load_request(
        self, *, tenant_id: str, run_id: str, request_id: str
    ) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        request = self._requests.get((tenant, run_id, request_id))
        if request is None:
            raise ApprovalRequestNotFoundError(f"approval request not found: {request_id}")
        if request.request_hash != request_hash(request):
            raise ApprovalRequestTamperedError(f"approval request tampered: {request_id}")
        return request

    def list_requests(self, *, tenant_id: str, run_id: str) -> list[ApprovalRequest]:
        tenant = validate_tenant_id(tenant_id)
        return [
            item
            for (stored_tenant, stored_run, _), item in sorted(self._requests.items())
            if stored_tenant == tenant and stored_run == run_id
        ]

    def list_pending_requests(self, *, tenant_id: str, run_id: str) -> list[ApprovalRequest]:
        return [item for item in self.list_requests(tenant_id=tenant_id, run_id=run_id) if item.status == "pending"]

    def decide_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision: ApprovalDecision,
        decision_actor: str,
        decision_note: str = "",
    ) -> ApprovalRequest:
        if decision_actor.startswith("model:"):
            raise PermissionError("model actors cannot approve their own requests")
        request = self.load_request(tenant_id=tenant_id, run_id=run_id, request_id=request_id)
        if request.status not in {"pending", "evidence_requested"} and decision in {
            "approved",
            "rejected",
        }:
            raise RequestAlreadyConsumedError(f"approval request already decided: {request_id}")
        previous_request = request
        updated = request.model_copy(
            update={
                "status": decision,
                "decision_at": _utc_now(),
                "decision_actor": decision_actor,
                "decision_note": decision_note,
            }
        )
        updated = updated.model_copy(update={"request_hash": request_hash(updated)})
        self._requests[(validate_tenant_id(tenant_id), run_id, request_id)] = updated
        if decision == "approved":
            grant = Grant(
                grant_id=grant_id_for_request(updated),
                run_id=updated.run_id,
                request_id=updated.request_id,
                tenant_id=updated.tenant_id,
                action=updated.action,
                policy_snapshot_id=updated.policy_snapshot_id,
                target=updated.target,
                created_at=updated.decision_at or _utc_now(),
            )
            self.save_grant(tenant_id=tenant_id, grant=grant)
        elif decision == "revoked" and previous_request.status == "approved":
            grant_id = grant_id_for_request(previous_request)
            grant = self.load_grant(
                tenant_id=tenant_id,
                run_id=run_id,
                grant_id=grant_id,
            )
            revoked = grant.model_copy(update={"revoked_at": updated.decision_at or _utc_now()})
            revoked = revoked.model_copy(update={"grant_hash": grant_hash(revoked)})
            self._grants[(validate_tenant_id(tenant_id), run_id, grant_id)] = revoked
        return updated

    def request_evidence(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision_actor: str,
        decision_note: str,
    ) -> ApprovalRequest:
        if not decision_note.strip():
            raise ValueError("evidence request requires a note")
        return self.decide_request(
            tenant_id=tenant_id,
            run_id=run_id,
            request_id=request_id,
            decision="evidence_requested",
            decision_actor=decision_actor,
            decision_note=decision_note,
        )

    def revoke_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision_actor: str,
        decision_note: str = "",
    ) -> ApprovalRequest:
        return self.decide_request(
            tenant_id=tenant_id,
            run_id=run_id,
            request_id=request_id,
            decision="revoked",
            decision_actor=decision_actor,
            decision_note=decision_note,
        )

    def save_grant(self, *, tenant_id: str, grant: Grant) -> Grant:
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, grant.tenant_id, operation="save_grant")
        validate_grant_id(grant.grant_id)
        key = (tenant, grant.run_id, grant.grant_id)
        if key in self._grants:
            raise ApprovalRequestExistsError(f"grant exists: {grant.grant_id}")
        stored = grant.model_copy(update={"grant_hash": grant_hash(grant)})
        self._grants[key] = stored
        return stored

    def load_grant(self, *, tenant_id: str, run_id: str, grant_id: str) -> Grant:
        tenant = validate_tenant_id(tenant_id)
        grant = self._grants.get((tenant, run_id, grant_id))
        if grant is None:
            raise ApprovalRequestNotFoundError(f"grant not found: {grant_id}")
        if grant.grant_hash != grant_hash(grant):
            raise ApprovalRequestTamperedError(f"grant tampered: {grant_id}")
        return grant

    def consume_grant(self, *, tenant_id: str, run_id: str, grant_id: str) -> Grant:
        grant = self.load_grant(tenant_id=tenant_id, run_id=run_id, grant_id=grant_id)
        if grant.revoked_at is not None or grant.consumed_at is not None:
            raise GrantAlreadyConsumedError(f"grant already consumed: {grant_id}")
        updated = grant.model_copy(update={"consumed_at": _utc_now()})
        updated = updated.model_copy(update={"grant_hash": grant_hash(updated)})
        self._grants[(validate_tenant_id(tenant_id), run_id, grant_id)] = updated
        return updated

    def validate_approved_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        action: Action,
        policy_snapshot_id: str,
        target: dict[str, str],
    ) -> tuple[ApprovalRequest, Grant]:
        tenant = validate_tenant_id(tenant_id)
        request = self.load_request(tenant_id=tenant, run_id=run_id, request_id=request_id)
        if request.status != "approved":
            raise PermissionError(f"approval request is not approved: {request_id}")
        expected = (tenant, action, policy_snapshot_id, target)
        actual = (request.tenant_id, request.action, request.policy_snapshot_id, request.target)
        if actual != expected:
            raise PermissionError(f"approval request binding mismatch: {request_id}")
        grant = self.load_grant(
            tenant_id=tenant, run_id=run_id, grant_id=grant_id_for_request(request)
        )
        grant_binding = (grant.tenant_id, grant.action, grant.policy_snapshot_id, grant.target)
        if grant.request_id != request.request_id or grant_binding != expected:
            raise PermissionError(f"approval grant binding mismatch: {grant.grant_id}")
        if grant.revoked_at is not None or grant.consumed_at is not None:
            raise GrantAlreadyConsumedError(f"approval grant unavailable: {grant.grant_id}")
        return request, grant

    def consume_approved_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        action: Action,
        policy_snapshot_id: str,
        target: dict[str, str],
    ) -> Grant:
        _, grant = self.validate_approved_request(
            tenant_id=tenant_id,
            run_id=run_id,
            request_id=request_id,
            action=action,
            policy_snapshot_id=policy_snapshot_id,
            target=target,
        )
        return self.consume_grant(tenant_id=tenant_id, run_id=run_id, grant_id=grant.grant_id)


class StrictFakeAuditStore:
    def __init__(self, sac_root: Path) -> None:
        self._events: list[AuditEvent] = []
        self._local = LocalAuditStore(sac_root)

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
    ) -> AuditEvent:
        tenant = validate_tenant_id(tenant_id)
        event = self._local.emit(
            kind,
            tenant_id=tenant,
            run_id=run_id,
            actor_id=actor_id,
            payload=payload,
            status=status,
            message=message,
        )
        self._events.append(event)
        return event

    def verify_integrity(self) -> tuple[bool, str]:
        return self._local.verify_integrity()

    def list_events(self, *, tenant_id: str, run_id: str | None = None) -> list[AuditEvent]:
        tenant = validate_tenant_id(tenant_id)
        return [
            event
            for event in self._events
            if event.metadata.get("tenant_id") == tenant
            and (run_id is None or event.metadata.get("run_id") == run_id)
        ]

    def tamper_first_event_for_test(self) -> None:
        self._local.tamper_first_event_for_test()


@dataclass
class StrictFakeBackend:
    """In-memory protocol fake with artifact-backed trace/evidence stores."""

    sac_root: Path
    runs: StrictFakeRunStore = field(default_factory=StrictFakeRunStore)
    approvals: StrictFakeApprovalStore = field(default_factory=StrictFakeApprovalStore)

    def __post_init__(self) -> None:
        self.audit = StrictFakeAuditStore(self.sac_root)
        self._trace = LocalTraceStore(self.sac_root)
        self._eval = LocalEvalResultStore(self.sac_root)
        self._evidence_bridge = _StrictFakeEvidenceStore(self)

    @property
    def eval_results(self) -> LocalEvalResultStore:
        return self._eval

    @property
    def trace(self) -> _StrictFakeTraceBridge:
        return _StrictFakeTraceBridge(self)

    @property
    def evidence(self) -> _StrictFakeEvidenceStore:
        return self._evidence_bridge


@dataclass
class _StrictFakeTraceBridge:
    backend: StrictFakeBackend

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
    ) -> TraceEvent | None:
        checkpoint = self.backend.runs.load_checkpoint(tenant_id=tenant_id, run_id=run_id)
        from safecode.enterprise.persistence.local_backend import LocalRunStore

        LocalRunStore(self.backend.sac_root).save_checkpoint(
            tenant_id=tenant_id, checkpoint=checkpoint
        )
        return self.backend._trace.emit_event(
            tenant_id=tenant_id,
            run_id=run_id,
            event_type=event_type,
            node_id=node_id,
            seq=seq,
            payload=payload,
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            cost=cost,
            duration_ms=duration_ms,
            event_id=event_id,
            timestamp=timestamp,
        )

    def list_events(self, *, tenant_id: str, run_id: str) -> list[TraceEvent]:
        return self.backend._trace.list_events(tenant_id=tenant_id, run_id=run_id)

    def write_timeline(self, *, tenant_id: str, run_id: str) -> Path:
        checkpoint = self.backend.runs.load_checkpoint(tenant_id=tenant_id, run_id=run_id)
        from safecode.enterprise.persistence.local_backend import LocalRunStore

        LocalRunStore(self.backend.sac_root).save_checkpoint(
            tenant_id=tenant_id, checkpoint=checkpoint
        )
        return self.backend._trace.write_timeline(tenant_id=tenant_id, run_id=run_id)


@dataclass
class _StrictFakeEvidenceStore:
    backend: StrictFakeBackend

    def export_run_evidence(self, *, tenant_id: str, run_id: str) -> Path:
        checkpoint = self.backend.runs.load_checkpoint(tenant_id=tenant_id, run_id=run_id)
        from safecode.enterprise.persistence.local_backend import LocalRunStore

        LocalRunStore(self.backend.sac_root).save_checkpoint(
            tenant_id=tenant_id, checkpoint=checkpoint
        )
        store = LocalEvidenceStore(self.backend.sac_root)
        return store.export_run_evidence(tenant_id=tenant_id, run_id=run_id)
