"""LocalBackend adapter tests (v2.1.2-T2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.enterprise.persistence.exceptions import TenantBoundaryError
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.persistence.protocols import (
    ApprovalStore,
    AuditStore,
    EvalResultStore,
    EvidenceStore,
    RunStore,
    TraceStore,
)
from safecode.enterprise.workflow.exceptions import InvalidRunIdError
from safecode.enterprise.workflow.checkpoint import RunCheckpoint
from safecode.enterprise.rbac.models import RBACSubject
from safecode.enterprise.workflow.state import EnterpriseRunState, RepoContext, RunRequest
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus


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


@pytest.mark.parametrize(
    ("protocol", "accessor"),
    [
        (RunStore, lambda backend: backend.runs),
        (ApprovalStore, lambda backend: backend.approvals),
        (AuditStore, lambda backend: backend.audit),
        (EvidenceStore, lambda backend: backend.evidence),
        (EvalResultStore, lambda backend: backend.eval_results),
        (TraceStore, lambda backend: backend.trace),
    ],
)
def test_local_backend_exposes_protocol_stores(protocol, accessor, tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    assert isinstance(accessor(backend), protocol)


def test_local_backend_rejects_cross_tenant_checkpoint_load(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    state = _sample_state(tenant_id="tenant-a")
    checkpoint = RunCheckpoint(
        schema_version="1.2.0",
        run_id=state.run_id,
        completed_nodes=[],
        next_node="classify_request",
        state=state,
    )
    backend.runs.save_checkpoint(tenant_id="tenant-a", checkpoint=checkpoint)
    with pytest.raises(TenantBoundaryError):
        backend.runs.load_checkpoint(tenant_id="tenant-b", run_id=state.run_id)


def test_local_backend_rejects_cross_tenant_decide_before_write(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from backend_contract import sample_request  # noqa: E402

    backend = LocalBackend(tmp_path / ".sac")
    run_id = "run-tenant-decide01"
    request = sample_request(run_id=run_id, request_id="approval-tenant-dec01", tenant_id="tenant-a")
    backend.approvals.save_request(tenant_id="tenant-a", request=request)
    with pytest.raises(TenantBoundaryError):
        backend.approvals.decide_request(
            tenant_id="tenant-b",
            run_id=run_id,
            request_id=request.request_id,
            decision="approved",
            decision_actor="user:approver",
        )
    loaded = backend.approvals.load_request(
        tenant_id="tenant-a", run_id=run_id, request_id=request.request_id
    )
    assert loaded.status == "pending"


def test_invalid_run_id_outside_run_root_fails_closed(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    with pytest.raises(InvalidRunIdError):
        backend.runs.load_checkpoint(tenant_id="local", run_id="../escape")
