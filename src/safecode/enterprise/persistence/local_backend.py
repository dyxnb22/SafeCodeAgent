"""File-backed persistence adapter implementing v2.1.2 repository protocols."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from safecode.audit.models import AuditEvent
from safecode.enterprise.approvals.store import (
    Action,
    ApprovalRequest,
    Grant,
    consume_approved_request,
    consume_grant,
    decide_request,
    list_pending_requests,
    list_requests,
    load_grant,
    load_request,
    request_evidence,
    revoke_request,
    save_grant,
    save_request,
    validate_approved_request,
)
from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.audit.tenant import filter_audit_events_by_tenant
from safecode.enterprise.eval.cases import EvaluationResult
from safecode.enterprise.persistence.protocols import (
    ApprovalDecision,
    assert_tenant_match,
    validate_tenant_id,
)
from safecode.enterprise.persistence.webhook_store import LocalWebhookEventStore
from safecode.enterprise.trace.emitter import TraceEmitter
from safecode.enterprise.trace.events import TraceEvent, TraceEventType
from safecode.enterprise.trace.session import project_root_for_sac
from safecode.enterprise.trace.timeline import write_timeline
from safecode.enterprise.workflow.checkpoint import (
    RunCheckpoint,
    gc_runs,
    load_checkpoint,
    run_dir,
    save_checkpoint,
)
from safecode.enterprise.workflow.exceptions import CheckpointCorruptedError
from safecode.enterprise.workflow.contracts import NodeCost
from safecode.enterprise.workflow.ids import validate_run_id

if TYPE_CHECKING:
    from safecode.enterprise.worker.lease import LocalRunLeaseStore
    from safecode.enterprise.worker.queue import LocalCommandQueue


class LocalRunStore:
    """Local filesystem run checkpoint store."""

    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def save_checkpoint(self, *, tenant_id: str, checkpoint: RunCheckpoint) -> None:
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, checkpoint.state.tenant_id, operation="save_checkpoint")
        save_checkpoint(self.sac_root, checkpoint)

    def load_checkpoint(self, *, tenant_id: str, run_id: str) -> RunCheckpoint:
        tenant = validate_tenant_id(tenant_id)
        checkpoint = load_checkpoint(self.sac_root, run_id)
        assert_tenant_match(tenant, checkpoint.state.tenant_id, operation="load_checkpoint")
        return checkpoint

    def resolve_run_tenant(self, *, run_id: str) -> str:
        validate_run_id(run_id)
        checkpoint = load_checkpoint(self.sac_root, run_id)
        return validate_tenant_id(checkpoint.state.tenant_id)

    def purge_run(self, *, tenant_id: str, run_id: str) -> None:
        tenant = validate_tenant_id(tenant_id)
        validate_run_id(run_id)
        directory = run_dir(self.sac_root, run_id)
        if not directory.is_dir():
            return
        if directory.is_dir() and (directory / "state.json").is_file():
            checkpoint = load_checkpoint(self.sac_root, run_id)
            assert_tenant_match(tenant, checkpoint.state.tenant_id, operation="purge_run")
        shutil.rmtree(directory)

    def gc_runs(self, *, tenant_id: str, older_than_days: int) -> list[str]:
        validate_tenant_id(tenant_id)
        return gc_runs(self.sac_root, older_than_days=older_than_days)


class LocalApprovalStore:
    """Local filesystem approval and grant store."""

    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def save_request(self, *, tenant_id: str, request: ApprovalRequest) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, request.tenant_id, operation="save_request")
        return save_request(self.sac_root, request)

    def load_request(
        self, *, tenant_id: str, run_id: str, request_id: str
    ) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        request = load_request(self.sac_root, run_id, request_id)
        assert_tenant_match(tenant, request.tenant_id, operation="load_request")
        return request

    def list_requests(self, *, tenant_id: str, run_id: str) -> list[ApprovalRequest]:
        tenant = validate_tenant_id(tenant_id)
        return [item for item in list_requests(self.sac_root, run_id) if item.tenant_id == tenant]

    def list_pending_requests(self, *, tenant_id: str, run_id: str) -> list[ApprovalRequest]:
        tenant = validate_tenant_id(tenant_id)
        return [
            item
            for item in list_pending_requests(self.sac_root, run_id)
            if item.tenant_id == tenant
        ]

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
        tenant = validate_tenant_id(tenant_id)
        request = decide_request(
            self.sac_root,
            run_id,
            request_id,
            decision=decision,
            decision_actor=decision_actor,
            decision_note=decision_note,
        )
        assert_tenant_match(tenant, request.tenant_id, operation="decide_request")
        return request

    def request_evidence(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision_actor: str,
        decision_note: str,
    ) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        request = request_evidence(
            self.sac_root,
            run_id,
            request_id,
            decision_actor=decision_actor,
            decision_note=decision_note,
        )
        assert_tenant_match(tenant, request.tenant_id, operation="request_evidence")
        return request

    def revoke_request(
        self,
        *,
        tenant_id: str,
        run_id: str,
        request_id: str,
        decision_actor: str,
        decision_note: str = "",
    ) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        request = revoke_request(
            self.sac_root,
            run_id,
            request_id,
            decision_actor=decision_actor,
            decision_note=decision_note,
        )
        assert_tenant_match(tenant, request.tenant_id, operation="revoke_request")
        return request

    def save_grant(self, *, tenant_id: str, grant: Grant) -> Grant:
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, grant.tenant_id, operation="save_grant")
        return save_grant(self.sac_root, grant)

    def load_grant(self, *, tenant_id: str, run_id: str, grant_id: str) -> Grant:
        tenant = validate_tenant_id(tenant_id)
        grant = load_grant(self.sac_root, run_id, grant_id)
        assert_tenant_match(tenant, grant.tenant_id, operation="load_grant")
        return grant

    def consume_grant(self, *, tenant_id: str, run_id: str, grant_id: str) -> Grant:
        tenant = validate_tenant_id(tenant_id)
        grant = consume_grant(self.sac_root, run_id, grant_id)
        assert_tenant_match(tenant, grant.tenant_id, operation="consume_grant")
        return grant

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
        request, grant = validate_approved_request(
            self.sac_root,
            run_id,
            request_id,
            tenant_id=tenant,
            action=action,
            policy_snapshot_id=policy_snapshot_id,
            target=target,
        )
        assert_tenant_match(tenant, request.tenant_id, operation="validate_approved_request")
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
        tenant = validate_tenant_id(tenant_id)
        grant = consume_approved_request(
            self.sac_root,
            run_id,
            request_id,
            tenant_id=tenant,
            action=action,
            policy_snapshot_id=policy_snapshot_id,
            target=target,
        )
        assert_tenant_match(tenant, grant.tenant_id, operation="consume_approved_request")
        return grant


class LocalAuditStore:
    """Local filesystem audit hash-chain store."""

    def __init__(self, sac_root: Path) -> None:
        self._chain = EnterpriseAuditChain(project_root_for_sac(sac_root))

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
        return self._chain.emit(
            kind,
            tenant_id=validate_tenant_id(tenant_id),
            run_id=run_id,
            actor_id=actor_id,
            payload=payload,
            status=status,
            message=message,
        )

    def verify_integrity(self) -> tuple[bool, str]:
        return self._chain.verify_integrity()

    def list_events(self, *, tenant_id: str, run_id: str | None = None) -> list[AuditEvent]:
        return filter_audit_events_by_tenant(
            self._chain.iter_events(),
            validate_tenant_id(tenant_id),
            run_id=run_id,
        )

    def tamper_first_event_for_test(self) -> None:
        if not self._chain.log_file.is_file():
            raise RuntimeError("no audit events to tamper")
        lines = self._chain.log_file.read_text(encoding="utf-8").splitlines()
        payload = json.loads(lines[0])
        payload["message"] = "tampered"
        lines[0] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self._chain.log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


class LocalEvidenceStore:
    """Local filesystem evidence bundle store."""

    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def export_run_evidence(self, *, tenant_id: str, run_id: str) -> Path:
        from safecode.enterprise.evidence.export import export_run_evidence

        return export_run_evidence(
            self.sac_root,
            run_id,
            tenant_id=validate_tenant_id(tenant_id),
        )


class LocalEvalResultStore:
    """Local filesystem evaluation result store."""

    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def write_results(
        self, *, tenant_id: str, run_id: str, results: list[EvaluationResult]
    ) -> Path:
        validate_tenant_id(tenant_id)
        from safecode.enterprise.eval.runner import write_results as persist_eval_results

        return persist_eval_results(results, self.sac_root, run_id)

    def read_results(self, *, tenant_id: str, run_id: str) -> list[EvaluationResult]:
        validate_tenant_id(tenant_id)
        path = self.sac_root / "enterprise" / "eval" / "results" / run_id / "results.json"
        if not path.is_file():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [EvaluationResult.model_validate(item) for item in payload]


class LocalTraceStore:
    """Local filesystem trace and timeline store."""

    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

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
        emitter = TraceEmitter(self.sac_root, run_id)
        return emitter.emit(
            event_type,
            node_id=node_id,
            seq=seq,
            tenant_id=validate_tenant_id(tenant_id),
            payload=payload,
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            cost=cost,
            duration_ms=duration_ms,
            event_id=event_id,
            timestamp=timestamp,
        )

    def list_events(self, *, tenant_id: str, run_id: str) -> list[TraceEvent]:
        tenant = validate_tenant_id(tenant_id)
        return [
            item
            for item in TraceEmitter(self.sac_root, run_id).iter_events()
            if item.tenant_id == tenant
        ]

    def write_timeline(self, *, tenant_id: str, run_id: str) -> Path:
        validate_tenant_id(tenant_id)
        return write_timeline(self.sac_root, run_id)


@dataclass(frozen=True)
class LocalBackend:
    """Aggregate local filesystem persistence surface for Enterprise workflows."""

    sac_root: Path

    @property
    def runs(self) -> LocalRunStore:
        return LocalRunStore(self.sac_root)

    @property
    def approvals(self) -> LocalApprovalStore:
        return LocalApprovalStore(self.sac_root)

    @property
    def audit(self) -> LocalAuditStore:
        return LocalAuditStore(self.sac_root)

    @property
    def evidence(self) -> LocalEvidenceStore:
        return LocalEvidenceStore(self.sac_root)

    @property
    def eval_results(self) -> LocalEvalResultStore:
        return LocalEvalResultStore(self.sac_root)

    @property
    def trace(self) -> LocalTraceStore:
        return LocalTraceStore(self.sac_root)

    @property
    def commands(self) -> LocalCommandQueue:
        from safecode.enterprise.worker.queue import LocalCommandQueue

        return LocalCommandQueue(self.sac_root)

    @property
    def leases(self) -> LocalRunLeaseStore:
        from safecode.enterprise.worker.lease import LocalRunLeaseStore

        return LocalRunLeaseStore(self.sac_root)

    @property
    def webhooks(self) -> LocalWebhookEventStore:
        return LocalWebhookEventStore(self.sac_root)

    def probe(self) -> bool:
        """Return whether the local backend storage is usable."""
        try:
            target = self.sac_root / "enterprise"
            target.mkdir(parents=True, exist_ok=True)
            probe_file = target / ".probe"
            probe_file.write_text("ok", encoding="utf-8")
            return probe_file.is_file()
        except OSError:
            return False
