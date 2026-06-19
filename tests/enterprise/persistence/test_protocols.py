"""Persistence protocol contract tests (v2.1.2-T1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.enterprise.persistence.exceptions import MissingTenantIdError, TenantBoundaryError
from safecode.enterprise.persistence.local_backend import LocalBackend
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
from safecode.enterprise.rbac.models import RBACSubject
from safecode.enterprise.workflow.checkpoint import RunCheckpoint
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
def test_local_backend_satisfies_protocols(protocol, accessor, tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    assert isinstance(accessor(backend), protocol)


def test_protocols_are_subclassable() -> None:
    class ExplicitRunStore(RunStore):
        def save_checkpoint(self, *, tenant_id: str, checkpoint: RunCheckpoint) -> None:
            validate_tenant_id(tenant_id)

        def load_checkpoint(self, *, tenant_id: str, run_id: str) -> RunCheckpoint:
            validate_tenant_id(tenant_id)
            raise NotImplementedError

        def resolve_run_tenant(self, *, run_id: str) -> str:
            validate_tenant_id("local")
            return "local"

        def purge_run(self, *, tenant_id: str, run_id: str) -> None:
            validate_tenant_id(tenant_id)

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


def test_run_store_round_trips_checkpoint(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    state = _sample_state()
    checkpoint = RunCheckpoint(
        schema_version="1.2.0",
        run_id=state.run_id,
        completed_nodes=[],
        next_node="classify_request",
        state=state,
    )
    backend.runs.save_checkpoint(tenant_id="local", checkpoint=checkpoint)
    loaded = backend.runs.load_checkpoint(tenant_id="local", run_id=state.run_id)
    assert loaded.state.run_id == state.run_id


def test_all_v2_write_paths_have_protocol_methods() -> None:
    run_methods = {name for name in RunStore.__dict__ if not name.startswith("_")}
    approval_methods = {name for name in ApprovalStore.__dict__ if not name.startswith("_")}
    audit_methods = {name for name in AuditStore.__dict__ if not name.startswith("_")}
    evidence_methods = {name for name in EvidenceStore.__dict__ if not name.startswith("_")}
    eval_methods = {name for name in EvalResultStore.__dict__ if not name.startswith("_")}
    trace_methods = {name for name in TraceStore.__dict__ if not name.startswith("_")}

    assert run_methods >= {
        "save_checkpoint",
        "load_checkpoint",
        "resolve_run_tenant",
        "purge_run",
        "gc_runs",
    }
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
