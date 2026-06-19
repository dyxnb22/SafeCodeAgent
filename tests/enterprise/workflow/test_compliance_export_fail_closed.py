"""Regression tests for compliance_export workflow fail-closed behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli_enterprise import enterprise_app
from safecode.enterprise.workflow.exceptions import UnsupportedWorkflowTaskError
from safecode.enterprise.workflow.orchestrator import (
    COMPLIANCE_EXPORT_UNSUPPORTED_MSG,
    LocalOrchestrator,
    build_initial_state,
    ensure_workflow_task_executable,
)
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.worker.commands import start_run
from safecode.enterprise.worker.queue import LocalCommandQueue


def test_ensure_workflow_task_executable_rejects_compliance_export() -> None:
    with pytest.raises(UnsupportedWorkflowTaskError, match="not implemented"):
        ensure_workflow_task_executable(TaskType.compliance_export)


def test_build_initial_state_rejects_compliance_export(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedWorkflowTaskError, match="not implemented"):
        build_initial_state(
            task_type=TaskType.compliance_export,
            input_ref="runs=run-01HX",
            actor_id="user:local",
            repo_root=tmp_path,
        )


def test_compliance_export_cli_workflow_run_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "workflow",
            "run",
            "--task",
            "compliance_export",
            "--input",
            str(fixture),
            "--root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "not implemented" in result.output
    assert COMPLIANCE_EXPORT_UNSUPPORTED_MSG.split(";")[0] in result.output


def test_compliance_export_orchestrator_marks_failed_not_pr_review(
    tmp_path: Path,
) -> None:
    sac_root = tmp_path / ".sac"
    orchestrator = LocalOrchestrator(sac_root)
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref=str(tmp_path / "fixture.json"),
        actor_id="user:local",
        repo_root=tmp_path,
    )
    state = state.model_copy(update={"task_type": TaskType.compliance_export})
    final = asyncio.run(orchestrator.run(state))
    assert final.status is WorkflowStatus.failed
    report = final.report
    assert report is None or report.kind != "pr_review_report"


def test_compliance_export_api_start_run_rejected(tmp_path: Path) -> None:
    settings = TeamServerSettings.model_validate(
        {"runtime_mode": RuntimeMode.LOCAL, "operator_actor": "user:dev"}
    )
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=lambda: RBACSubject(
            actor_id="user:dev", tenant_id="tenant-a", roles=(Role.developer,)
        ),
        project_root=tmp_path,
    )
    client = TestClient(app)
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    response = client.post(
        "/v2/runs",
        headers={"X-Tenant-Id": "tenant-a", "Idempotency-Key": "idem-compliance-export"},
        json={"task_type": "compliance_export", "input_ref": str(fixture)},
    )
    assert response.status_code == 400
    assert "not implemented" in response.json()["detail"]


def test_compliance_export_worker_start_run_rejected(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / ".sac")
    queue = LocalCommandQueue(backend.sac_root)
    subject = RBACSubject(actor_id="user:dev", tenant_id="tenant-a", roles=(Role.developer,))
    with pytest.raises(ValueError, match="not implemented"):
        start_run(
            backend,
            queue,
            tenant_id="tenant-a",
            idempotency_key="idem-worker-compliance",
            task_type="compliance_export",
            input_ref="runs=run-01HX",
            subject=subject,
            project_root=tmp_path,
        )


def test_compliance_export_does_not_map_to_pr_fixture_input_kind(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedWorkflowTaskError):
        build_initial_state(
            task_type=TaskType.compliance_export,
            input_ref="runs=run-01HX",
            actor_id="user:local",
            repo_root=tmp_path,
        )
    pr_state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref=str(tmp_path / "fixture.json"),
        actor_id="user:local",
        repo_root=tmp_path,
    )
    assert pr_state.request.input_kind == "pr_fixture"
