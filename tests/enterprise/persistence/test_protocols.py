"""Persistence protocol contract tests (v2.1.2-T1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
from safecode.enterprise.eval.runner import write_results
from safecode.enterprise.evidence.export import export_run_evidence
from safecode.enterprise.persistence.exceptions import MissingTenantIdError, TenantBoundaryError
from safecode.enterprise.persistence.protocols import (
    ApprovalStore,
    AuditStore,
    EvalResultStore,
    EvidenceStore,
    RunStore,
    TraceStore,
    assert_tenant_match,
    validate_tenant_id,
)
from safecode.enterprise.trace.emitter import TraceEmitter
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.trace.session import project_root_for_sac
from safecode.enterprise.trace.timeline import write_timeline
from safecode.enterprise.workflow.checkpoint import RunCheckpoint, load_checkpoint, save_checkpoint
from safecode.enterprise.workflow.contracts import NodeCost
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus
from safecode.enterprise.rbac.models import RBACSubject
from safecode.enterprise.workflow.state import EnterpriseRunState, RepoContext, RunRequest


class _FileRunStore:
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

    def gc_runs(self, *, tenant_id: str, older_than_days: int) -> list[str]:
        validate_tenant_id(tenant_id)
        from safecode.enterprise.workflow.checkpoint import gc_runs

        return gc_runs(self.sac_root, older_than_days=older_than_days)


class _FileApprovalStore:
    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def save_request(self, *, tenant_id: str, request: ApprovalRequest) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        assert_tenant_match(tenant, request.tenant_id, operation="save_request")
        return save_request(self.sac_root, request)

    def load_request(self, *, tenant_id: str, run_id: str, request_id: str) -> ApprovalRequest:
        tenant = validate_tenant_id(tenant_id)
        request = load_request(self.sac_root, run_id, request_id)
        assert_tenant_match(tenant, request.tenant_id, operation="load_request")
        return request

    def list_requests(self, *, tenant_id: str, run_id: str) -> list[ApprovalRequest]:
        tenant = validate_tenant_id(tenant_id)
        return [
            item
            for item in list_requests(self.sac_root, run_id)
            if item.tenant_id == tenant
        ]

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
        decision,
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


class _FileAuditStore:
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


class _FileEvidenceStore:
    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def export_run_evidence(self, *, tenant_id: str, run_id: str) -> Path:
        return export_run_evidence(self.sac_root, run_id, tenant_id=validate_tenant_id(tenant_id))


class _FileEvalResultStore:
    def __init__(self, sac_root: Path) -> None:
        self.sac_root = sac_root

    def write_results(
        self, *, tenant_id: str, run_id: str, results: list[EvaluationResult]
    ) -> Path:
        validate_tenant_id(tenant_id)
        return write_results(results, self.sac_root, run_id)

    def read_results(self, *, tenant_id: str, run_id: str) -> list[EvaluationResult]:
        validate_tenant_id(tenant_id)
        path = self.sac_root / "enterprise" / "eval" / "results" / run_id / "results.json"
        if not path.is_file():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [EvaluationResult.model_validate(item) for item in payload]


class _FileTraceStore:
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
    ):
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

    def list_events(self, *, tenant_id: str, run_id: str):
        tenant = validate_tenant_id(tenant_id)
        return [
            item
            for item in TraceEmitter(self.sac_root, run_id).iter_events()
            if item.tenant_id == tenant
        ]

    def write_timeline(self, *, tenant_id: str, run_id: str) -> Path:
        validate_tenant_id(tenant_id)
        return write_timeline(self.sac_root, run_id)


@pytest.mark.parametrize(
    ("protocol", "adapter"),
    [
        (RunStore, _FileRunStore),
        (ApprovalStore, _FileApprovalStore),
        (AuditStore, _FileAuditStore),
        (EvidenceStore, _FileEvidenceStore),
        (EvalResultStore, _FileEvalResultStore),
        (TraceStore, _FileTraceStore),
    ],
)
def test_v2_file_adapters_satisfy_protocols(protocol, adapter, tmp_path: Path) -> None:
    sac_root = tmp_path / ".sac"
    sac_root.mkdir()
    instance = adapter(sac_root)
    assert isinstance(instance, protocol)


def test_protocols_are_subclassable() -> None:
    class ExplicitRunStore(RunStore):
        def save_checkpoint(self, *, tenant_id: str, checkpoint: RunCheckpoint) -> None:
            validate_tenant_id(tenant_id)

        def load_checkpoint(self, *, tenant_id: str, run_id: str) -> RunCheckpoint:
            validate_tenant_id(tenant_id)
            raise NotImplementedError

        def gc_runs(self, *, tenant_id: str, older_than_days: int) -> list[str]:
            validate_tenant_id(tenant_id)
            return []

    assert isinstance(ExplicitRunStore(), RunStore)


@pytest.mark.parametrize("tenant_id", [None, "", "   "])
def test_validate_tenant_id_rejects_missing_values(tenant_id) -> None:
    with pytest.raises(MissingTenantIdError, match="tenant_id is required"):
        validate_tenant_id(tenant_id)


def test_assert_tenant_match_raises_on_cross_tenant_access() -> None:
    with pytest.raises(TenantBoundaryError, match="tenant mismatch"):
        assert_tenant_match("tenant-a", "tenant-b", operation="load_checkpoint")


def _sample_state(run_id: str = "run-test123456", tenant_id: str = "local") -> EnterpriseRunState:
    now = "2026-06-19T00:00:00+00:00"
    return EnterpriseRunState(
        run_id=run_id,
        tenant_id=tenant_id,
        task_type=TaskType.pr_review,
        status=WorkflowStatus.pending,
        actor_id="user:test",
        subject=RBACSubject(actor_id="user:test", tenant_id=tenant_id),
        policy_snapshot_id="policy-test",
        request=RunRequest(
            task_type=TaskType.pr_review,
            input_kind="pr_fixture",
            input_ref="examples/enterprise/fixtures/pr_benign/pr.json",
            actor_id="user:test",
        ),
        repo=RepoContext(repo_root=str(Path("/tmp/repo"))),
        created_at=now,
        updated_at=now,
    )


def test_run_store_adapter_round_trips_checkpoint(tmp_path: Path) -> None:
    sac_root = tmp_path / ".sac"
    store = _FileRunStore(sac_root)
    state = _sample_state()
    checkpoint = RunCheckpoint(
        schema_version="1.2.0",
        run_id=state.run_id,
        completed_nodes=[],
        next_node="classify_request",
        state=state,
    )
    store.save_checkpoint(tenant_id="local", checkpoint=checkpoint)
    loaded = store.load_checkpoint(tenant_id="local", run_id=state.run_id)
    assert loaded.state.run_id == state.run_id


def test_all_v2_write_paths_have_protocol_methods() -> None:
    run_methods = {name for name in RunStore.__dict__ if not name.startswith("_")}
    approval_methods = {name for name in ApprovalStore.__dict__ if not name.startswith("_")}
    audit_methods = {name for name in AuditStore.__dict__ if not name.startswith("_")}
    evidence_methods = {name for name in EvidenceStore.__dict__ if not name.startswith("_")}
    eval_methods = {name for name in EvalResultStore.__dict__ if not name.startswith("_")}
    trace_methods = {name for name in TraceStore.__dict__ if not name.startswith("_")}

    assert run_methods >= {"save_checkpoint", "load_checkpoint", "gc_runs"}
    assert approval_methods >= {
        "save_request",
        "load_request",
        "list_requests",
        "list_pending_requests",
        "decide_request",
        "request_evidence",
        "revoke_request",
        "save_grant",
        "load_grant",
        "consume_grant",
        "validate_approved_request",
        "consume_approved_request",
    }
    assert audit_methods >= {"emit", "verify_integrity", "list_events"}
    assert evidence_methods >= {"export_run_evidence"}
    assert eval_methods >= {"write_results", "read_results"}
    assert trace_methods >= {"emit_event", "list_events", "write_timeline"}
