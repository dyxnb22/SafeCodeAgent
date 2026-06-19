"""Governed long-term memory offline tests (v2.4.6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.approvals.store import (
    Action,
    ApprovalRequest,
    decide_request,
    save_request,
)
from safecode.enterprise.memory.chunks import active_memory_chunks, memory_fact_to_chunk
from safecode.enterprise.memory.store import (
    MemoryFactStore,
    MemoryGovernanceError,
    memory_admission_target,
)
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.trace.session import project_root_for_sac
from safecode.enterprise.workflow.types import RiskTier

_TENANT = "tenant-a"
_RUN_ID = "run-memorytest01"
_POLICY = "policy-memory-test"


def _utc_offset(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).replace(microsecond=0).isoformat()


def _utc_future(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).replace(microsecond=0).isoformat()


def _admit(
    store: MemoryFactStore,
    *,
    tenant_id: str = _TENANT,
    content: str,
    provenance: str,
    fact_id: str,
    expires_at: str | None = None,
) -> object:
    expiry = expires_at or _utc_future(60)
    request_id = f"approval-memory-{fact_id.removeprefix('fact-')}"
    target = memory_admission_target(
        content=content,
        provenance=provenance,
        expires_at=expiry,
    )
    save_request(
        store.sac_root,
        ApprovalRequest(
            request_id=request_id,
            run_id=_RUN_ID,
            tenant_id=tenant_id,
            action=Action.memory_fact_inject,
            risk_tier=RiskTier.high,
            requested_by_node="memory_admission",
            requesting_actor="agent:memory",
            target=target,
            preview=content,
            policy_snapshot_id=_POLICY,
            created_at="2026-06-19T00:00:00+00:00",
        ),
    )
    decide_request(
        store.sac_root,
        _RUN_ID,
        request_id,
        decision="approved",
        decision_actor="user:security-reviewer",
    )
    return store.admit(
        tenant_id=tenant_id,
        content=content,
        provenance=provenance,
        actor_id="user:security-reviewer",
        run_id=_RUN_ID,
        request_id=request_id,
        policy_snapshot_id=_POLICY,
        expires_at=expiry,
        fact_id=fact_id,
    )


def test_admit_fact_records_audit_and_retrieval_chunk(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    store = MemoryFactStore(sac_root)
    fact = _admit(
        store,
        content="Rotate service credentials quarterly.",
        provenance="run:run-abc123",
        fact_id="fact-rotate-01",
    )
    assert fact.status == "active"
    assert fact.approver == "user:security-reviewer"
    assert fact.approval_grant_id.startswith("grant-")
    chunk = memory_fact_to_chunk(fact)
    assert chunk.permission_scope
    assert "memory://" in chunk.path
    chunks = active_memory_chunks(store, _TENANT)
    assert len(chunks) == 1
    retriever = HybridRetriever(chunks=chunks)
    citations = retriever.retrieve("rotate credentials", 3, ["org", "appsec"], actor_tenant=_TENANT)
    assert citations
    audit = EnterpriseAuditChain(project_root_for_sac(sac_root))
    events = audit.iter_events()
    assert any(
        event.type == AuditEventKind.tool_call_executed.value
        and event.metadata.get("operation") == "memory_fact_admitted"
        for event in events
    )


def test_revoke_removes_fact_from_active_retrieval(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    store = MemoryFactStore(sac_root)
    _admit(
        store,
        content="Legacy auth module deprecated.",
        provenance="manual-review",
        fact_id="fact-revoke-01",
    )
    revoked = store.revoke(tenant_id=_TENANT, fact_id="fact-revoke-01", actor_id="user:appsec")
    assert revoked.status == "revoked"
    assert revoked.revoked_at
    assert store.list_active(_TENANT) == []
    audit = EnterpriseAuditChain(project_root_for_sac(sac_root))
    assert any(
        event.metadata.get("operation") == "memory_fact_revoked" for event in audit.iter_events()
    )


def test_expire_due_facts(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    store = MemoryFactStore(sac_root)
    _admit(
        store,
        content="Temporary waiver for scanner rule X.",
        provenance="approval:waiver-12",
        fact_id="fact-expire-01",
        expires_at=_utc_offset(5),
    )
    expired = store.expire_due(tenant_id=_TENANT, actor_id="system:memory")
    assert len(expired) == 1
    assert expired[0].status == "expired"
    assert store.list_active(_TENANT) == []


def test_admit_requires_approver_and_provenance(tmp_path: Path):
    store = MemoryFactStore(tmp_path / ".sac")
    with pytest.raises(MemoryGovernanceError, match="provenance"):
        store.admit(
            tenant_id=_TENANT,
            content="test",
            provenance="",
            actor_id="user:test",
            run_id=_RUN_ID,
            request_id="approval-memory-invalid",
            policy_snapshot_id=_POLICY,
            expires_at=_utc_future(60),
        )


def test_cross_tenant_isolation(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    store = MemoryFactStore(sac_root)
    _admit(
        store,
        tenant_id="tenant-a",
        content="Tenant A fact",
        provenance="run:a",
        fact_id="fact-a",
    )
    _admit(
        store,
        tenant_id="tenant-b",
        content="Tenant B fact",
        provenance="run:b",
        fact_id="fact-b",
    )
    assert len(store.list_active("tenant-a")) == 1
    assert store.list_active("tenant-a")[0].fact_id == "fact-a"
    assert store.get(tenant_id="tenant-b", fact_id="fact-a") is None


def test_future_expiry_stays_active(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    store = MemoryFactStore(sac_root)
    _admit(
        store,
        content="Valid until next quarter.",
        provenance="policy-review",
        fact_id="fact-future-01",
        expires_at=_utc_future(60),
    )
    store.expire_due(tenant_id=_TENANT, actor_id="system:memory")
    assert len(store.list_active(_TENANT)) == 1


def test_tenant_path_escape_is_rejected_without_writing(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    store = MemoryFactStore(sac_root)
    with pytest.raises(Exception, match="tenant_id"):
        store.admit(
            tenant_id="../../outside",
            content="untrusted fact",
            provenance="untrusted",
            actor_id="user:attacker",
            run_id=_RUN_ID,
            request_id="approval-memory-escape",
            policy_snapshot_id=_POLICY,
            expires_at=_utc_future(60),
            fact_id="fact-escape",
        )
    assert not (tmp_path / "outside.json").exists()


def test_memory_admission_without_bound_grant_fails_closed(tmp_path: Path):
    store = MemoryFactStore(tmp_path / ".sac")
    with pytest.raises(MemoryGovernanceError, match="grant denied"):
        store.admit(
            tenant_id=_TENANT,
            content="unapproved persistent instruction",
            provenance="model:output",
            actor_id="model:planner",
            run_id=_RUN_ID,
            request_id="approval-memory-missing",
            policy_snapshot_id=_POLICY,
            expires_at=_utc_future(60),
            fact_id="fact-unapproved",
        )
