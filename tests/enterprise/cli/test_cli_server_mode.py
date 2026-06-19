"""CLI server-mode tests (v2.1.5-T4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from safecode.cli_enterprise import enterprise_app
from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.client.api_client import (
    ServerModeError,
    load_bearer_token,
    reject_raw_token_argv,
)
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.worker.runner import WorkerRunner

_ROOT = Path(__file__).resolve().parents[3]


def test_reject_raw_token_argv() -> None:
    with pytest.raises(ServerModeError):
        reject_raw_token_argv(["workflow", "run", "eyJhbGciOiJIUzI1NiIs.abc.def"])


def test_load_bearer_token_from_env(monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_ENTERPRISE_TOKEN", "env-token")
    assert load_bearer_token() == "env-token"


def test_server_mode_missing_token_fails(tmp_path: Path, monkeypatch) -> None:
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
            "pr_review",
            "--input",
            str(fixture),
            "--root",
            str(tmp_path),
            "--server-url",
            "http://127.0.0.1:8080",
        ],
        env={},
    )
    assert result.exit_code == 1
    assert "token" in result.output.lower()


def test_server_mode_rejects_actor_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAFECODE_ENTERPRISE_TOKEN", "env-token")
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        enterprise_app,
        [
            "workflow",
            "run",
            "--task",
            "pr_review",
            "--input",
            str(fixture),
            "--root",
            str(tmp_path),
            "--server-url",
            "http://127.0.0.1:8080",
            "--actor",
            "user:bad",
        ],
    )
    assert result.exit_code == 1
    assert "server mode rejects --actor" in result.output


def test_local_and_server_mode_parity_for_fixture_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fixture = tmp_path / "fixture.json"
    fixture.write_text("{}", encoding="utf-8")

    runner = CliRunner()
    local = runner.invoke(
        enterprise_app,
        [
            "workflow",
            "run",
            "--task",
            "pr_review",
            "--input",
            str(fixture),
            "--root",
            str(tmp_path),
        ],
    )
    assert local.exit_code == 0
    local_status = json.loads(local.stdout)["status"]

    settings = TeamServerSettings.model_validate(
        {"runtime_mode": RuntimeMode.LOCAL, "operator_actor": "user:dev"}
    )
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=settings,
        backend=backend,
        subject_resolver=lambda: RBACSubject(
            actor_id="user:dev", tenant_id="local", roles=(Role.developer,)
        ),
        project_root=tmp_path,
    )
    test_client = TestClient(app)

    class _TestApiClient:
        def __init__(self, **_: object) -> None:
            pass

        def start_run(self, *, task_type: str, input_ref: str, idempotency_key: str) -> dict[str, object]:
            response = test_client.post(
                "/v2/runs",
                headers={
                    "X-Tenant-Id": "local",
                    "Idempotency-Key": idempotency_key,
                },
                json={"task_type": task_type, "input_ref": input_ref},
            )
            if response.status_code >= 400:
                raise ServerModeError(response.text)
            return response.json()

    monkeypatch.setenv("SAFECODE_ENTERPRISE_TOKEN", "env-token")
    monkeypatch.setattr("safecode.cli_enterprise.EnterpriseApiClient", _TestApiClient)
    server = runner.invoke(
        enterprise_app,
        [
            "workflow",
            "run",
            "--task",
            "pr_review",
            "--input",
            str(fixture),
            "--root",
            str(tmp_path),
            "--server-url",
            "http://testserver",
        ],
    )
    assert server.exit_code == 0, f"stdout={server.stdout!r} stderr={server.stderr!r}"
    run_id = json.loads(server.stdout)["run_id"]
    worker = WorkerRunner(backend, worker_id="worker-test", project_root=tmp_path)
    for _ in range(20):
        worker.process_once()
        status = backend.runs.load_checkpoint(tenant_id="local", run_id=run_id).state.status.value
        if status in {"succeeded", "awaiting_approval", "failed", "cancelled"}:
            break
    final_status = backend.runs.load_checkpoint(tenant_id="local", run_id=run_id).state.status.value
    assert final_status == local_status
