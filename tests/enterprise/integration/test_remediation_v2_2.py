"""Offline v2.2 remediation integration suite (v2.2.5-T2)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

_INTEGRATION_DIR = Path(__file__).resolve().parent
if str(_INTEGRATION_DIR) not in sys.path:
    sys.path.insert(0, str(_INTEGRATION_DIR))

from _v2_2_helpers import (
    OWNER,
    RECORDED_TOKEN,
    REPO,
    TENANT_ID,
    integration_client,
    repo_root,
    signed_ci_callback,
)

from safecode.enterprise.approvals.store import (
    Action,
    ApprovalRequest,
    decide_request,
    save_request,
)
from safecode.enterprise.connectors.github_branch import (
    BranchPushSpec,
    PRCreateSpec,
    branch_push_target,
    execute_secure_change,
    namespaced_branch_name,
    pr_create_target,
    push_branch_governed,
)
from safecode.enterprise.workflow.exceptions import WorkflowInterrupted
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator, build_initial_state
from safecode.enterprise.workflow.types import RiskTier, TaskType, WorkflowStatus

pytestmark = [pytest.mark.integration]

_ROOT = Path(__file__).resolve().parents[3]
_REMEDIATION_FIXTURE = "examples/enterprise/fixtures/remediation/sql_injection"
_RUN_ID = "run-remediation-v22"
_COMMIT_SHA = "abc123def4567890abc123def4567890abc12345"
_PATCH_DIGEST = "patch-digest-remediation-v22"
_BRANCH_REQUEST_ID = "approval-run-remediation-v22-branch"
_PR_REQUEST_ID = "approval-run-remediation-v22-pr"
_PR_NUMBER = 101
_ACCESS_TOKEN = RECORDED_TOKEN
_POLICY = "snapshot-test"


def _branch_name() -> str:
    return namespaced_branch_name(_RUN_ID)


def _branch_spec(**overrides: object) -> BranchPushSpec:
    base = {
        "owner": OWNER,
        "repo": REPO,
        "base_branch": "main",
        "branch_name": _branch_name(),
        "commit_sha": _COMMIT_SHA,
        "patch_digest": _PATCH_DIGEST,
        "api_base_url": "https://api.github.com",
    }
    base.update(overrides)
    return BranchPushSpec.model_validate(base)


def _pr_spec(**overrides: object) -> PRCreateSpec:
    base = {
        "owner": OWNER,
        "repo": REPO,
        "head_branch": _branch_name(),
        "base_branch": "main",
        "title": "Safe remediation for SQL injection",
        "body": "Automated fix with tests.",
        "api_base_url": "https://api.github.com",
    }
    base.update(overrides)
    return PRCreateSpec.model_validate(base)


def _recorded_remediation_transport(*, calls: list[str] | None = None) -> httpx.MockTransport:
    observed: list[str] = calls if calls is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(f"{request.method} {request.url.path}")
        if request.method == "POST" and request.url.path.endswith("/git/refs"):
            return httpx.Response(
                201,
                json={
                    "ref": f"refs/heads/{_branch_name()}",
                    "object": {"sha": _COMMIT_SHA, "type": "commit"},
                },
            )
        if request.method == "POST" and request.url.path.endswith("/pulls"):
            return httpx.Response(
                201,
                json={
                    "number": _PR_NUMBER,
                    "html_url": f"https://github.com/{OWNER}/{REPO}/pull/{_PR_NUMBER}",
                    "head": {"ref": _branch_name()},
                    "base": {"ref": "main"},
                },
            )
        return httpx.Response(404, json={"message": "Not Found"})

    return httpx.MockTransport(handler)


def _approve_branch_push(sac_root: Path, *, tenant_id: str = TENANT_ID) -> None:
    spec = _branch_spec()
    request = ApprovalRequest(
        request_id=_BRANCH_REQUEST_ID,
        run_id=_RUN_ID,
        tenant_id=tenant_id,
        action=Action.github_branch_push,
        risk_tier=RiskTier.high,
        requested_by_node="finalize",
        requesting_actor="user:approver",
        target=branch_push_target(spec),
        preview=f"push {_branch_name()}",
        policy_snapshot_id=_POLICY,
        created_at="2026-06-19T00:00:00+00:00",
    )
    save_request(sac_root, request)
    decide_request(
        sac_root,
        _RUN_ID,
        _BRANCH_REQUEST_ID,
        decision="approved",
        decision_actor="user:reviewer",
    )


def _approve_pr_create(sac_root: Path, *, tenant_id: str = TENANT_ID) -> None:
    spec = _pr_spec()
    request = ApprovalRequest(
        request_id=_PR_REQUEST_ID,
        run_id=_RUN_ID,
        tenant_id=tenant_id,
        action=Action.github_pr_create,
        risk_tier=RiskTier.high,
        requested_by_node="finalize",
        requesting_actor="user:approver",
        target=pr_create_target(spec),
        preview=f"open PR from {_branch_name()}",
        policy_snapshot_id=_POLICY,
        created_at="2026-06-19T00:00:00+00:00",
    )
    save_request(sac_root, request)
    decide_request(
        sac_root,
        _RUN_ID,
        _PR_REQUEST_ID,
        decision="approved",
        decision_actor="user:reviewer",
    )


def _run_remediation_until_approval(project_root: Path) -> Path:
    sac_root = project_root / ".sac"
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    state = build_initial_state(
        task_type=TaskType.remediation,
        input_ref=_REMEDIATION_FIXTURE,
        actor_id="user:security",
        repo_root=project_root,
        run_id=_RUN_ID,
        tenant_id=TENANT_ID,
    )
    with pytest.raises(WorkflowInterrupted):
        asyncio.run(orchestrator.run(state))
    return sac_root


def test_offline_recorded_remediation_creates_one_branch_and_pr(tmp_path: Path) -> None:
    project_root = repo_root(tmp_path)
    sac_root = _run_remediation_until_approval(project_root)
    decide_request(
        sac_root,
        _RUN_ID,
        f"approval-{_RUN_ID}",
        decision="approved",
        decision_actor="user:reviewer",
    )
    orchestrator = LocalOrchestrator(sac_root, runtime="local")
    final = asyncio.run(orchestrator.resume(_RUN_ID, tenant_id=TENANT_ID))
    assert final.status is WorkflowStatus.succeeded

    patch_props = [item for item in final.proposals if item.kind == "patch"]
    assert patch_props

    _approve_branch_push(sac_root)
    _approve_pr_create(sac_root)
    calls: list[str] = []
    transport = _recorded_remediation_transport(calls=calls)

    branch_record, pr_record, outcome = execute_secure_change(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        branch_spec=_branch_spec(),
        pr_spec=_pr_spec(),
        actor_id="user:approver",
        tenant_id=TENANT_ID,
        policy_snapshot_id=_POLICY,
        branch_push_request_id=_BRANCH_REQUEST_ID,
        pr_create_request_id=_PR_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )

    assert branch_record.outcome == "ok"
    assert pr_record.outcome == "ok"
    assert outcome.pull_request.pr_number == _PR_NUMBER
    ref_calls = [call for call in calls if call.endswith("/git/refs")]
    pr_calls = [call for call in calls if call.endswith("/pulls")]
    assert len(ref_calls) == 1
    assert len(pr_calls) == 1


def test_patch_change_blocks_branch_push(tmp_path: Path) -> None:
    project_root = repo_root(tmp_path)
    sac_root = _run_remediation_until_approval(project_root)
    _approve_branch_push(sac_root)
    calls: list[str] = []
    transport = _recorded_remediation_transport(calls=calls)

    record = push_branch_governed(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=_branch_spec(patch_digest="changed-after-approval"),
        actor_id="user:approver",
        tenant_id=TENANT_ID,
        policy_snapshot_id=_POLICY,
        branch_push_request_id=_BRANCH_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )

    assert record.outcome == "blocked"
    assert calls == []


def test_protected_branch_blocks_push(tmp_path: Path) -> None:
    project_root = repo_root(tmp_path)
    sac_root = _run_remediation_until_approval(project_root)
    protected_spec = _branch_spec(branch_name="main")
    request = ApprovalRequest(
        request_id=_BRANCH_REQUEST_ID,
        run_id=_RUN_ID,
        tenant_id=TENANT_ID,
        action=Action.github_branch_push,
        risk_tier=RiskTier.high,
        requested_by_node="finalize",
        requesting_actor="user:approver",
        target=branch_push_target(protected_spec),
        preview="push main",
        policy_snapshot_id=_POLICY,
        created_at="2026-06-19T00:00:00+00:00",
    )
    save_request(sac_root, request)
    decide_request(
        sac_root,
        _RUN_ID,
        _BRANCH_REQUEST_ID,
        decision="approved",
        decision_actor="user:reviewer",
    )
    calls: list[str] = []
    transport = _recorded_remediation_transport(calls=calls)

    record = push_branch_governed(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=protected_spec,
        actor_id="user:approver",
        tenant_id=TENANT_ID,
        policy_snapshot_id=_POLICY,
        branch_push_request_id=_BRANCH_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )

    assert record.outcome == "blocked"
    assert calls == []


def test_duplicate_callback_fails_closed(tmp_path: Path) -> None:
    client, _backend = integration_client(tmp_path)
    project_root = repo_root(tmp_path)
    sac_root = _run_remediation_until_approval(project_root)
    from safecode.enterprise.persistence.local_backend import LocalBackend
    from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint

    shared_backend = LocalBackend(sac_root)
    checkpoint = shared_backend.runs.load_checkpoint(tenant_id=TENANT_ID, run_id=_RUN_ID)
    state = checkpoint.state.model_copy(
        update={
            "repo": checkpoint.state.repo.model_copy(update={"commit_sha": "b" * 40}),
        }
    )
    shared_backend.runs.save_checkpoint(
        tenant_id=TENANT_ID,
        checkpoint=RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=_RUN_ID,
            completed_nodes=list(checkpoint.completed_nodes),
            next_node=checkpoint.next_node,
            state=state,
        ),
    )

    delivery_id = "ci-remediation-dup01"
    first = signed_ci_callback(client, run_id=_RUN_ID, delivery_id=delivery_id, commit_sha="b" * 40)
    assert first.status_code == 202
    second = signed_ci_callback(client, run_id=_RUN_ID, delivery_id=delivery_id, commit_sha="b" * 40)
    assert second.status_code == 202
    assert second.json()["replay"] == "true"

    shared_backend.webhooks.record_delivery(
        delivery_id="ci-remediation-conflict",
        tenant_id=TENANT_ID,
        event_type="ci_callback",
        run_id="run-other000000001",
        idempotency_key="ci-remediation-conflict",
        payload_digest="abc123",
    )
    conflict = signed_ci_callback(
        client,
        run_id=_RUN_ID,
        delivery_id="ci-remediation-conflict",
    )
    assert conflict.status_code == 409
