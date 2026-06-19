"""Shared persistence contract exercises for any Enterprise backend."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

import pytest

from safecode.enterprise.approvals.store import (
    Action,
    ApprovalRequest,
    Grant,
    GrantAlreadyConsumedError,
    grant_id_for_request,
)
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.eval.cases import EvaluationResult
from safecode.enterprise.evidence.export import verify_export_bundle
from safecode.enterprise.persistence.exceptions import TenantBoundaryError
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.persistence.strict_fake import StrictFakeBackend
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.workflow.checkpoint import RunCheckpoint
from safecode.enterprise.workflow.exceptions import (
    ApprovalRequestExistsError,
    InvalidRunIdError,
)
from safecode.enterprise.rbac.models import RBACSubject
from safecode.enterprise.workflow.state import EnterpriseRunState, RepoContext, RunRequest
from safecode.enterprise.workflow.types import RiskTier, TaskType, WorkflowStatus


class BackendFactory(Protocol):
    def __call__(self, tmp_path: Path) -> LocalBackend | StrictFakeBackend: ...


@dataclass(frozen=True)
class BackendBundle:
    backend: LocalBackend | StrictFakeBackend
    sac_root: Path
    tenant_id: str = "tenant-a"
    alt_tenant_id: str = "tenant-b"


def sample_state(
    *,
    run_id: str = "run-contract001",
    tenant_id: str = "tenant-a",
) -> EnterpriseRunState:
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


def sample_checkpoint(
    *,
    run_id: str = "run-contract001",
    tenant_id: str = "tenant-a",
) -> RunCheckpoint:
    state = sample_state(run_id=run_id, tenant_id=tenant_id)
    return RunCheckpoint(
        schema_version="1.2.0",
        run_id=run_id,
        completed_nodes=[],
        next_node="classify_request",
        state=state,
    )


def sample_request(
    *,
    run_id: str = "run-contract001",
    request_id: str = "approval-run-contract001",
    tenant_id: str = "tenant-a",
) -> ApprovalRequest:
    return ApprovalRequest(
        request_id=request_id,
        run_id=run_id,
        tenant_id=tenant_id,
        action=Action.file_write,
        risk_tier=RiskTier.high,
        requested_by_node="approval_gate",
        requesting_actor="user:test",
        policy_snapshot_id="snapshot-local",
        created_at="2026-06-19T00:00:00+00:00",
        preview="write config.py",
    )


def make_bundle(factory: BackendFactory, tmp_path: Path) -> BackendBundle:
    sac_root = tmp_path / ".sac"
    backend = factory(sac_root)
    return BackendBundle(backend=backend, sac_root=sac_root)


def exercise_run_checkpoint_round_trip(bundle: BackendBundle) -> None:
    checkpoint = sample_checkpoint(tenant_id=bundle.tenant_id)
    bundle.backend.runs.save_checkpoint(tenant_id=bundle.tenant_id, checkpoint=checkpoint)
    loaded = bundle.backend.runs.load_checkpoint(
        tenant_id=bundle.tenant_id, run_id=checkpoint.run_id
    )
    assert loaded.state.run_id == checkpoint.run_id
    assert loaded.state.tenant_id == bundle.tenant_id


def exercise_cross_tenant_checkpoint_denied(bundle: BackendBundle) -> None:
    checkpoint = sample_checkpoint(tenant_id=bundle.tenant_id)
    bundle.backend.runs.save_checkpoint(tenant_id=bundle.tenant_id, checkpoint=checkpoint)
    with pytest.raises(TenantBoundaryError):
        bundle.backend.runs.load_checkpoint(
            tenant_id=bundle.alt_tenant_id, run_id=checkpoint.run_id
        )


def exercise_invalid_run_id_denied(bundle: BackendBundle) -> None:
    with pytest.raises(InvalidRunIdError):
        bundle.backend.runs.load_checkpoint(tenant_id=bundle.tenant_id, run_id="../escape")


def exercise_approval_and_grant_lifecycle(bundle: BackendBundle) -> None:
    run_id = "run-contract001"
    request = sample_request(run_id=run_id, tenant_id=bundle.tenant_id)
    saved = bundle.backend.approvals.save_request(tenant_id=bundle.tenant_id, request=request)
    assert saved.status == "pending"

    decided = bundle.backend.approvals.decide_request(
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        request_id=saved.request_id,
        decision="approved",
        decision_actor="user:reviewer",
    )
    assert decided.status == "approved"

    grant = bundle.backend.approvals.load_grant(
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        grant_id=grant_id_for_request(decided),
    )
    assert grant.consumed_at is None

    target = dict(decided.target)
    validated_request, validated_grant = bundle.backend.approvals.validate_approved_request(
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        request_id=saved.request_id,
        action=decided.action,
        policy_snapshot_id=decided.policy_snapshot_id,
        target=target,
    )
    assert validated_request.request_id == saved.request_id
    assert validated_grant.grant_id == grant.grant_id

    consumed = bundle.backend.approvals.consume_approved_request(
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        request_id=saved.request_id,
        action=decided.action,
        policy_snapshot_id=decided.policy_snapshot_id,
        target=target,
    )
    assert consumed.consumed_at is not None


def exercise_duplicate_grant_consumption_denied(bundle: BackendBundle) -> None:
    run_id = "run-grant00001"
    grant = Grant(
        grant_id="grant-run-grant00001",
        run_id=run_id,
        request_id="approval-run-grant00001",
        tenant_id=bundle.tenant_id,
        action=Action.file_write,
        policy_snapshot_id="snapshot-local",
        created_at="2026-06-19T00:00:00+00:00",
    )
    saved = bundle.backend.approvals.save_grant(tenant_id=bundle.tenant_id, grant=grant)
    bundle.backend.approvals.consume_grant(
        tenant_id=bundle.tenant_id, run_id=run_id, grant_id=saved.grant_id
    )
    with pytest.raises(GrantAlreadyConsumedError):
        bundle.backend.approvals.consume_grant(
            tenant_id=bundle.tenant_id, run_id=run_id, grant_id=saved.grant_id
        )


def exercise_revoked_request_revokes_grant(bundle: BackendBundle) -> None:
    run_id = "run-revokegrant01"
    request = sample_request(
        run_id=run_id,
        request_id="approval-revokegrant01",
        tenant_id=bundle.tenant_id,
    )
    saved = bundle.backend.approvals.save_request(
        tenant_id=bundle.tenant_id,
        request=request,
    )
    approved = bundle.backend.approvals.decide_request(
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        request_id=saved.request_id,
        decision="approved",
        decision_actor="user:reviewer",
    )
    grant_id = grant_id_for_request(approved)

    revoked = bundle.backend.approvals.revoke_request(
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        request_id=saved.request_id,
        decision_actor="user:reviewer",
    )

    assert revoked.status == "revoked"
    grant = bundle.backend.approvals.load_grant(
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        grant_id=grant_id,
    )
    assert grant.revoked_at is not None
    with pytest.raises(GrantAlreadyConsumedError):
        bundle.backend.approvals.consume_grant(
            tenant_id=bundle.tenant_id,
            run_id=run_id,
            grant_id=grant_id,
        )


def exercise_duplicate_request_denied(bundle: BackendBundle) -> None:
    request = sample_request(
        run_id="run-dupreq001",
        request_id="approval-run-dupreq001",
        tenant_id=bundle.tenant_id,
    )
    bundle.backend.approvals.save_request(tenant_id=bundle.tenant_id, request=request)
    with pytest.raises(ApprovalRequestExistsError):
        bundle.backend.approvals.save_request(tenant_id=bundle.tenant_id, request=request)


def exercise_audit_chain_append_and_verify(bundle: BackendBundle) -> None:
    run_id = "run-audit00001"
    bundle.backend.audit.emit(
        AuditEventKind.workflow_start,
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        actor_id="user:test",
    )
    bundle.backend.audit.emit(
        AuditEventKind.workflow_end,
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        actor_id="user:test",
    )
    ok, message = bundle.backend.audit.verify_integrity()
    assert ok, message
    events = bundle.backend.audit.list_events(tenant_id=bundle.tenant_id, run_id=run_id)
    assert len(events) == 2


def exercise_corrupted_audit_fails_verification(bundle: BackendBundle) -> None:
    run_id = "run-auditcorrupt1"
    bundle.backend.audit.emit(
        AuditEventKind.workflow_start,
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        actor_id="user:test",
    )
    if hasattr(bundle.backend.audit, "tamper_first_event_for_test"):
        bundle.backend.audit.tamper_first_event_for_test()
    else:
        audit = bundle.backend.audit
        chain = getattr(audit, "_chain", None)
        if chain is None or not chain.log_file.is_file():
            pytest.skip("backend does not expose a tamperable local audit log")
        lines = chain.log_file.read_text(encoding="utf-8").splitlines()
        payload = json.loads(lines[0])
        payload["message"] = "tampered"
        lines[0] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        chain.log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, _message = bundle.backend.audit.verify_integrity()
    assert not ok


def exercise_eval_results_round_trip(bundle: BackendBundle) -> None:
    run_id = "run-eval000001"
    results = [
        EvaluationResult(
            case_id="case-smoke-001",
            suite="smoke",
            passed=True,
            notes="contract",
        )
    ]
    path = bundle.backend.eval_results.write_results(
        tenant_id=bundle.tenant_id, run_id=run_id, results=results
    )
    assert path.is_file()
    loaded = bundle.backend.eval_results.read_results(
        tenant_id=bundle.tenant_id, run_id=run_id
    )
    assert len(loaded) == 1
    assert loaded[0].case_id == "case-smoke-001"


def exercise_trace_round_trip(bundle: BackendBundle) -> None:
    run_id = "run-trace00001"
    checkpoint = sample_checkpoint(run_id=run_id, tenant_id=bundle.tenant_id)
    bundle.backend.runs.save_checkpoint(tenant_id=bundle.tenant_id, checkpoint=checkpoint)
    event = bundle.backend.trace.emit_event(
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        event_type=TraceEventType.node_start,
        node_id="classify_request",
        seq=1,
        payload={"phase": "contract"},
    )
    assert event is not None
    events = bundle.backend.trace.list_events(tenant_id=bundle.tenant_id, run_id=run_id)
    assert len(events) == 1
    timeline_path = bundle.backend.trace.write_timeline(
        tenant_id=bundle.tenant_id, run_id=run_id
    )
    assert timeline_path.is_file()


def exercise_evidence_export(bundle: BackendBundle) -> None:
    run_id = "run-evidence001"
    checkpoint = sample_checkpoint(run_id=run_id, tenant_id=bundle.tenant_id)
    bundle.backend.runs.save_checkpoint(tenant_id=bundle.tenant_id, checkpoint=checkpoint)
    bundle.backend.audit.emit(
        AuditEventKind.workflow_start,
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        actor_id="user:test",
    )
    bundle.backend.trace.emit_event(
        tenant_id=bundle.tenant_id,
        run_id=run_id,
        event_type=TraceEventType.node_start,
        node_id="classify_request",
        seq=1,
    )
    zip_path = bundle.backend.evidence.export_run_evidence(
        tenant_id=bundle.tenant_id, run_id=run_id
    )
    ok, message = verify_export_bundle(zip_path)
    assert ok, message


CONTRACT_EXERCISES: tuple[tuple[str, Callable[[BackendBundle], None]], ...] = (
    ("run_checkpoint_round_trip", exercise_run_checkpoint_round_trip),
    ("cross_tenant_checkpoint_denied", exercise_cross_tenant_checkpoint_denied),
    ("invalid_run_id_denied", exercise_invalid_run_id_denied),
    ("approval_and_grant_lifecycle", exercise_approval_and_grant_lifecycle),
    ("duplicate_grant_consumption_denied", exercise_duplicate_grant_consumption_denied),
    ("revoked_request_revokes_grant", exercise_revoked_request_revokes_grant),
    ("duplicate_request_denied", exercise_duplicate_request_denied),
    ("audit_chain_append_and_verify", exercise_audit_chain_append_and_verify),
    ("corrupted_audit_fails_verification", exercise_corrupted_audit_fails_verification),
    ("eval_results_round_trip", exercise_eval_results_round_trip),
    ("trace_round_trip", exercise_trace_round_trip),
    ("evidence_export", exercise_evidence_export),
)
