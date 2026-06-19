"""CLI tests for sac enterprise workflow resume tenant boundary (R4 Batch 3)."""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli_enterprise import enterprise_app
from safecode.enterprise.approvals.store import decide_request
from safecode.enterprise.persistence.exceptions import TenantBoundaryError
from safecode.enterprise.workflow.exceptions import TenantContextRequiredError, WorkflowInterrupted
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus


def _start_awaiting_approval_run(
    tmp_path: Path,
    *,
    run_id: str = "run-cli-resume1",
    tenant_id: str = "tenant-a",
) -> None:
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id=run_id,
        tenant_id=tenant_id,
        extra={"high_risk": "1"},
    )
    (tmp_path / "fixture.json").write_text("{}", encoding="utf-8")
    with pytest.raises(WorkflowInterrupted):
        asyncio.run(orchestrator.run(state))


def test_workflow_resume_without_tenant_fails(tmp_path: Path) -> None:
    _start_awaiting_approval_run(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        ["workflow", "resume", "run-cli-resume1", "--root", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "requires --tenant" in result.output


def test_workflow_resume_with_correct_tenant_succeeds(tmp_path: Path) -> None:
    _start_awaiting_approval_run(tmp_path)
    decide_request(
        tmp_path / ".sac",
        "run-cli-resume1",
        "approval-run-cli-resume1",
        decision="approved",
        decision_actor="user:approver",
    )
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "workflow",
            "resume",
            "run-cli-resume1",
            "--tenant",
            "tenant-a",
            "--root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == WorkflowStatus.succeeded.value


def test_workflow_resume_with_wrong_tenant_fails(tmp_path: Path) -> None:
    _start_awaiting_approval_run(tmp_path)
    decide_request(
        tmp_path / ".sac",
        "run-cli-resume1",
        "approval-run-cli-resume1",
        decision="approved",
        decision_actor="user:approver",
    )
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "workflow",
            "resume",
            "run-cli-resume1",
            "--tenant",
            "tenant-b",
            "--root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "tenant mismatch" in result.output.lower()


def test_workflow_resume_allow_tenant_infer_succeeds(tmp_path: Path) -> None:
    _start_awaiting_approval_run(tmp_path)
    decide_request(
        tmp_path / ".sac",
        "run-cli-resume1",
        "approval-run-cli-resume1",
        decision="approved",
        decision_actor="user:approver",
    )
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "workflow",
            "resume",
            "run-cli-resume1",
            "--allow-tenant-infer",
            "--root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == WorkflowStatus.succeeded.value


def test_workflow_resume_rejects_tenant_with_infer_override(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "workflow",
            "resume",
            "run-cli-resume1",
            "--tenant",
            "tenant-a",
            "--allow-tenant-infer",
            "--root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output


def test_orchestrator_resume_requires_tenant_context(tmp_path: Path) -> None:
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-tenantctx1",
        tenant_id="tenant-a",
    )
    from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint

    orchestrator.backend.runs.save_checkpoint(
        tenant_id="tenant-a",
        checkpoint=RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=state.run_id,
            completed_nodes=[],
            next_node="classify_request",
            state=state,
        ),
    )
    with pytest.raises(TenantContextRequiredError, match="requires tenant_id"):
        asyncio.run(orchestrator.resume("run-tenantctx1"))


def test_orchestrator_resume_has_no_tenant_inference_override() -> None:
    assert "allow_tenant_infer" not in inspect.signature(LocalOrchestrator.resume).parameters


def test_orchestrator_resume_rejects_wrong_tenant(tmp_path: Path) -> None:
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-tenantctx2",
        tenant_id="tenant-a",
    )
    from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint

    orchestrator.backend.runs.save_checkpoint(
        tenant_id="tenant-a",
        checkpoint=RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=state.run_id,
            completed_nodes=[],
            next_node="classify_request",
            state=state,
        ),
    )
    with pytest.raises(TenantBoundaryError, match="tenant mismatch"):
        asyncio.run(orchestrator.resume("run-tenantctx2", tenant_id="tenant-b"))
