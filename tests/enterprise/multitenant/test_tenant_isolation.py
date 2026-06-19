"""Multi-tenant isolation tests."""

import asyncio
import json
from pathlib import Path

from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.audit.tenant import filter_audit_events_by_tenant
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType
from safecode.enterprise.approvals.store import decide_request
from safecode.enterprise.workflow.exceptions import WorkflowInterrupted


def test_audit_events_isolated_by_tenant(tmp_path: Path):
    audit = EnterpriseAuditChain(tmp_path)
    audit.emit(
        AuditEventKind.workflow_start,
        run_id="run-tenant-a",
        actor_id="user:a",
        tenant_id="tenant-a",
    )
    audit.emit(
        AuditEventKind.workflow_start,
        run_id="run-tenant-b",
        actor_id="user:b",
        tenant_id="tenant-b",
    )
    events = audit.iter_events()
    tenant_a = filter_audit_events_by_tenant(events, "tenant-a")
    tenant_b = filter_audit_events_by_tenant(events, "tenant-b")
    assert len(tenant_a) == 1
    assert len(tenant_b) == 1
    assert tenant_a[0].metadata["run_id"] == "run-tenant-a"
    assert tenant_b[0].metadata["run_id"] == "run-tenant-b"


def test_workflow_run_carries_tenant_into_trace(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-tenant0001",
        tenant_id="tenant-acme",
    )
    final = asyncio.run(orchestrator.run(state))
    assert final.tenant_id == "tenant-acme"
    trace_path = sac_root / "enterprise" / "runs" / final.run_id / "trace.jsonl"
    assert trace_path.is_file()
    content = trace_path.read_text(encoding="utf-8")
    assert "tenant-acme" in content
    assert '"tenant_id":"tenant-acme"' in content or '"tenant_id": "tenant-acme"' in content


def test_approval_events_preserve_workflow_tenant(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    run_id = "run-tenantapprove1"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
        tenant_id="tenant-acme",
        extra={"high_risk": "1"},
    )
    try:
        asyncio.run(orchestrator.run(state))
    except WorkflowInterrupted:
        pass
    decide_request(
        sac_root,
        run_id,
        f"approval-{run_id}",
        decision="approved",
        decision_actor="user:approver",
    )
    asyncio.run(orchestrator.resume(run_id, tenant_id="tenant-acme"))
    events = [
        json.loads(line)
        for line in (sac_root / "enterprise" / "runs" / run_id / "trace.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    approval_events = [event for event in events if event["type"].startswith("approval.")]
    assert approval_events
    assert {event["tenant_id"] for event in approval_events} == {"tenant-acme"}
