"""Evidence export shape and integrity tests."""

import asyncio
import json
import zipfile
from pathlib import Path

import pytest

from safecode.enterprise.approvals.store import decide_request
from safecode.enterprise.evidence.export import export_run_evidence, verify_export_bundle
from safecode.enterprise.workflow.exceptions import WorkflowInterrupted
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType


def test_export_shape_and_hash_chain(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-evidence01",
        tenant_id="tenant-a",
    )
    asyncio.run(orchestrator.run(state))
    bundle = export_run_evidence(sac_root, state.run_id, tenant_id="tenant-a")
    assert bundle.is_file()
    ok, message = verify_export_bundle(bundle)
    assert ok, message
    with zipfile.ZipFile(bundle, "r") as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "trace.jsonl" in names
        assert "timeline.json" in names
        assert "state.json" in names
        assert "audit_chain.jsonl" in names
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["tenant_id"] == "tenant-a"
        assert manifest["run_id"] == state.run_id
        assert manifest["source_audit_chain_verified"] is True


def test_export_strictly_redacts_state_and_report(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    secret = "ghp_1234567890123456789012345678901234"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref=f"fixture-{secret}.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-evidence02",
    )
    asyncio.run(orchestrator.run(state))
    bundle = export_run_evidence(sac_root, state.run_id, tenant_id="local")
    with zipfile.ZipFile(bundle, "r") as archive:
        corpus = b"\n".join(archive.read(name) for name in archive.namelist())
    assert secret.encode() not in corpus


def test_export_rejects_cross_tenant_request(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-evidence03",
        tenant_id="tenant-a",
    )
    asyncio.run(LocalOrchestrator(sac_root, runtime="local").run(state))
    try:
        export_run_evidence(sac_root, state.run_id, tenant_id="tenant-b")
    except PermissionError:
        pass
    else:
        raise AssertionError("cross-tenant evidence export was not rejected")


def test_export_verifies_interleaved_global_audit_chain(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    first = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:first",
        repo_root=tmp_path,
        run_id="run-evidence04",
        extra={"high_risk": "1"},
    )
    with pytest.raises(WorkflowInterrupted):
        asyncio.run(orchestrator.run(first))
    second = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:second",
        repo_root=tmp_path,
        run_id="run-evidence05",
    )
    asyncio.run(orchestrator.run(second))
    decide_request(
        sac_root,
        first.run_id,
        f"approval-{first.run_id}",
        decision="approved",
        decision_actor="user:approver",
    )
    asyncio.run(orchestrator.resume(first.run_id))
    bundle = export_run_evidence(sac_root, first.run_id, tenant_id="local")
    assert verify_export_bundle(bundle)[0] is True
