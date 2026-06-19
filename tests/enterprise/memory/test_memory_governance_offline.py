"""Governed long-term memory offline tests (v2.4.6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.memory.chunks import active_memory_chunks, memory_fact_to_chunk
from safecode.enterprise.memory.store import MemoryFactStore, MemoryGovernanceError
from safecode.enterprise.rag.retriever import HybridRetriever
from safecode.enterprise.trace.session import project_root_for_sac

_TENANT = "tenant-a"


def _utc_offset(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).replace(microsecond=0).isoformat()


def _utc_future(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).replace(microsecond=0).isoformat()


def test_admit_fact_records_audit_and_retrieval_chunk(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    store = MemoryFactStore(sac_root)
    fact = store.admit(
        tenant_id=_TENANT,
        content="Rotate service credentials quarterly.",
        provenance="run:run-abc123",
        approver="user:security-lead",
        actor_id="user:security-lead",
        fact_id="fact-rotate-01",
    )
    assert fact.status == "active"
    assert fact.approver == "user:security-lead"
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
    store.admit(
        tenant_id=_TENANT,
        content="Legacy auth module deprecated.",
        provenance="manual-review",
        approver="user:appsec",
        actor_id="user:appsec",
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
    store.admit(
        tenant_id=_TENANT,
        content="Temporary waiver for scanner rule X.",
        provenance="approval:waiver-12",
        approver="user:compliance",
        actor_id="user:compliance",
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
            approver="user:test",
            actor_id="user:test",
        )


def test_cross_tenant_isolation(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    store = MemoryFactStore(sac_root)
    store.admit(
        tenant_id="tenant-a",
        content="Tenant A fact",
        provenance="run:a",
        approver="user:a",
        actor_id="user:a",
        fact_id="fact-a",
    )
    store.admit(
        tenant_id="tenant-b",
        content="Tenant B fact",
        provenance="run:b",
        approver="user:b",
        actor_id="user:b",
        fact_id="fact-b",
    )
    assert len(store.list_active("tenant-a")) == 1
    assert store.list_active("tenant-a")[0].fact_id == "fact-a"
    assert store.get(tenant_id="tenant-b", fact_id="fact-a") is None


def test_future_expiry_stays_active(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    store = MemoryFactStore(sac_root)
    store.admit(
        tenant_id=_TENANT,
        content="Valid until next quarter.",
        provenance="policy-review",
        approver="user:lead",
        actor_id="user:lead",
        fact_id="fact-future-01",
        expires_at=_utc_future(60),
    )
    store.expire_due(tenant_id=_TENANT, actor_id="system:memory")
    assert len(store.list_active(_TENANT)) == 1
