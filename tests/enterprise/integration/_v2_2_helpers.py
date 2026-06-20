"""Shared helpers for v2.2 offline integration suites."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from safecode.enterprise.api.app import create_app
from safecode.enterprise.api.settings import RuntimeMode, TeamServerSettings
from safecode.enterprise.approvals.store import decide_request
from safecode.enterprise.connectors.github_app import sign_webhook_body
from safecode.enterprise.connectors.session import (
    reset_github_access_token,
    reset_github_transport,
    set_github_access_token,
    set_github_transport,
)
from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.scanners.results import CI_CALLBACK_SCHEMA_VERSION, sign_ci_callback_body
from safecode.enterprise.worker.runner import WorkerRunner
from safecode.enterprise.workflow.types import WorkflowStatus

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LIVE_FIXTURES = _REPO_ROOT / "tests" / "enterprise" / "connectors" / "fixtures" / "live"
_PR_SQL_FIXTURE = _REPO_ROOT / "examples" / "enterprise" / "fixtures" / "pr_sql_injection"
_REMEDIATION_FIXTURE = _REPO_ROOT / "examples" / "enterprise" / "fixtures" / "remediation" / "sql_injection"

APP_ID = "123456"
INSTALLATION_ID = "987654"
WEBHOOK_SECRET = "integration-webhook-secret"
CALLBACK_SECRET = WEBHOOK_SECRET
TENANT_ID = "tenant-github"
DELIVERY_ID = "integration-delivery-01"
OWNER = "acme"
REPO = "webapp"
PR_NUMBER = 42
RECORDED_TOKEN = SecretStr("ghs_recorded_installation_token_for_integration")
COMMENT_ID = "987654321"
COMMIT_SHA = "a" * 40


def repo_root(tmp_path: Path) -> Path:
    """Copy enterprise examples into an isolated project root."""
    for name in ("examples", "product-planning"):
        source = _REPO_ROOT / name
        if source.is_dir():
            shutil.copytree(source, tmp_path / name, dirs_exist_ok=True)
    return tmp_path


def generate_private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def team_server_settings() -> TeamServerSettings:
    return TeamServerSettings.model_validate(
        {
            "runtime_mode": RuntimeMode.LOCAL,
            "operator_actor": "user:dev",
            "github_app_id": APP_ID,
            "github_installation_id": INSTALLATION_ID,
            "github_private_key_pem": generate_private_key_pem(),
            "github_webhook_secret": WEBHOOK_SECRET,
            "ci_callback_secret": CALLBACK_SECRET,
            "github_webhook_tenant_id": TENANT_ID,
        }
    )


def integration_client(tmp_path: Path) -> tuple[TestClient, LocalBackend]:
    backend = LocalBackend(tmp_path / ".sac")
    app = create_app(
        settings=team_server_settings(),
        backend=backend,
        subject_resolver=lambda: RBACSubject(
            actor_id="user:dev",
            tenant_id=TENANT_ID,
            roles=(Role.developer,),
        ),
        project_root=repo_root(tmp_path),
    )
    return TestClient(app), backend


def pull_request_webhook_payload(*, repo: str = f"{OWNER}/{REPO}") -> dict[str, object]:
    return {
        "action": "opened",
        "installation": {"id": int(INSTALLATION_ID)},
        "repository": {"full_name": repo},
        "pull_request": {"number": PR_NUMBER},
    }


def signed_github_webhook(
    client: TestClient,
    *,
    payload: dict[str, object],
    delivery_id: str = DELIVERY_ID,
) -> object:
    body = json.dumps(payload).encode("utf-8")
    return client.post(
        "/v2/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": sign_webhook_body(body, secret=WEBHOOK_SECRET),
            "Content-Type": "application/json",
        },
    )


def load_live_fixture(name: str) -> object:
    return json.loads((_LIVE_FIXTURES / name).read_text(encoding="utf-8"))


def recorded_pr_review_transport(
    *,
    calls: list[str] | None = None,
    pull_payload: object | None = None,
    files_payload: object | None = None,
    pull_status: int = 200,
    files_status: int = 200,
    include_comment: bool = True,
) -> httpx.MockTransport:
    observed: list[str] = calls if calls is not None else []
    pull = load_live_fixture("pull.json") if pull_payload is None else pull_payload
    files = load_live_fixture("files_page1.json") if files_payload is None else files_payload

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(f"{request.method} {request.url.path}")
        path = request.url.path
        if request.method == "POST" and path.endswith("/comments") and include_comment:
            return httpx.Response(
                201,
                json={
                    "id": int(COMMENT_ID),
                    "html_url": f"https://github.com/{OWNER}/{REPO}/issues/{PR_NUMBER}#issuecomment-{COMMENT_ID}",
                    "body": "Security review comment",
                },
            )
        if path.endswith(f"/repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}/files"):
            return httpx.Response(files_status, json=files)
        if path.endswith(f"/repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}"):
            return httpx.Response(pull_status, json=pull)
        return httpx.Response(404, json={"message": "Not Found"})

    return httpx.MockTransport(handler)


def activate_recorded_github_session(transport: httpx.MockTransport) -> tuple[object, object]:
    transport_token = set_github_transport(transport)
    access_token = set_github_access_token(RECORDED_TOKEN)
    return transport_token, access_token


def deactivate_recorded_github_session(transport_token: object, access_token: object) -> None:
    reset_github_transport(transport_token)
    reset_github_access_token(access_token)


def drain_worker(
    backend: LocalBackend,
    project_root: Path,
    *,
    tenant_id: str = TENANT_ID,
    run_id: str,
    max_rounds: int = 40,
) -> WorkflowStatus:
    worker = WorkerRunner(backend, worker_id="integration-worker", project_root=project_root)
    status = WorkflowStatus.pending
    for _ in range(max_rounds):
        processed = worker.process_once()
        checkpoint = backend.runs.load_checkpoint(tenant_id=tenant_id, run_id=run_id)
        status = checkpoint.state.status
        if status in {
            WorkflowStatus.succeeded,
            WorkflowStatus.failed,
            WorkflowStatus.blocked,
            WorkflowStatus.rejected,
            WorkflowStatus.cancelled,
        }:
            return status
        if status is WorkflowStatus.awaiting_approval and not processed:
            return status
    return status


def approve_run(backend: LocalBackend, run_id: str, *, tenant_id: str = TENANT_ID) -> None:
    decide_request(
        backend.sac_root,
        run_id,
        f"approval-{run_id}",
        decision="approved",
        decision_actor="user:reviewer",
    )
    backend.commands.enqueue_job(tenant_id=tenant_id, run_id=run_id, command="resume")


def signed_ci_callback(
    client: TestClient,
    *,
    run_id: str,
    commit_sha: str = COMMIT_SHA,
    delivery_id: str = "ci-integration-0001",
    tenant_id: str = TENANT_ID,
) -> object:
    payload = {
        "schema_version": CI_CALLBACK_SCHEMA_VERSION,
        "delivery_id": delivery_id,
        "run_id": run_id,
        "outcome": "passed",
        "commit_sha": commit_sha,
        "scanner": "semgrep",
        "tool_version": "1.90.0",
    }
    body = json.dumps(payload).encode("utf-8")
    return client.post(
        "/v2/ci/callback",
        content=body,
        headers={
            "X-Tenant-Id": tenant_id,
            "Idempotency-Key": delivery_id,
            "X-CI-Signature-256": sign_ci_callback_body(body, secret=CALLBACK_SECRET),
            "Content-Type": "application/json",
        },
    )
