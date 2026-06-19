"""Governed GitHub branch push and PR create tests (v2.2.3-T2)."""

from __future__ import annotations

import re

import httpx
from pydantic import SecretStr

from safecode.enterprise.approvals.store import (
    Action,
    ApprovalRequest,
    decide_request,
    save_request,
)
from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.connectors.github_app import assert_output_safe
from safecode.enterprise.connectors.github_branch import (
    BranchPushSpec,
    PRCreateSpec,
    branch_push_target,
    execute_secure_change,
    namespaced_branch_name,
    pr_create_target,
    push_branch_governed,
)
from safecode.enterprise.trace.session import project_root_for_sac
from safecode.enterprise.workflow.types import RiskTier

_OWNER = "acme"
_REPO = "webapp"
_RUN_ID = "run-branchlive01"
_TENANT = "tenant-a"
_POLICY = "snapshot-test"
_BRANCH_REQUEST_ID = "approval-run-branchlive01"
_PR_REQUEST_ID = "approval-run-branchlive02"
_ACCESS_TOKEN = SecretStr("ghs_recorded_installation_token_for_branch_push")
_COMMIT_SHA = "abc123def4567890abc123def4567890abc12345"
_PATCH_DIGEST = "patch-digest-fixed-for-test"
_BASE_BRANCH = "main"
_PR_NUMBER = 99
_TOKEN_RE = re.compile(r"gh[ps]_[A-Za-z0-9]{20,}")


def _branch_name() -> str:
    return namespaced_branch_name(_RUN_ID)


def _branch_spec(**overrides: object) -> BranchPushSpec:
    base = {
        "owner": _OWNER,
        "repo": _REPO,
        "base_branch": _BASE_BRANCH,
        "branch_name": _branch_name(),
        "commit_sha": _COMMIT_SHA,
        "patch_digest": _PATCH_DIGEST,
        "api_base_url": "https://api.github.com",
    }
    base.update(overrides)
    return BranchPushSpec.model_validate(base)


def _pr_spec(**overrides: object) -> PRCreateSpec:
    base = {
        "owner": _OWNER,
        "repo": _REPO,
        "head_branch": _branch_name(),
        "base_branch": _BASE_BRANCH,
        "title": "Safe remediation for SQL injection",
        "body": "Automated fix with tests.",
        "api_base_url": "https://api.github.com",
    }
    base.update(overrides)
    return PRCreateSpec.model_validate(base)


def _recorded_transport(*, calls: list[str] | None = None) -> httpx.MockTransport:
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
                    "html_url": f"https://github.com/{_OWNER}/{_REPO}/pull/{_PR_NUMBER}",
                    "head": {"ref": _branch_name()},
                    "base": {"ref": _BASE_BRANCH},
                },
            )
        return httpx.Response(404, json={"message": "Not Found"})

    return httpx.MockTransport(handler)


def _approve_branch_push(sac_root, *, tenant_id: str = _TENANT) -> None:
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


def _approve_pr_create(sac_root, *, tenant_id: str = _TENANT) -> None:
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


def test_approved_replay_creates_one_namespaced_branch_and_pr(tmp_path):
    sac_root = tmp_path / ".sac"
    _approve_branch_push(sac_root)
    _approve_pr_create(sac_root)
    calls: list[str] = []
    transport = _recorded_transport(calls=calls)

    branch_record, pr_record, outcome = execute_secure_change(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        branch_spec=_branch_spec(),
        pr_spec=_pr_spec(),
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        branch_push_request_id=_BRANCH_REQUEST_ID,
        pr_create_request_id=_PR_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )

    assert branch_record.outcome == "ok"
    assert pr_record.outcome == "ok"
    assert outcome.branch.branch_name == _branch_name()
    assert outcome.branch.branch_name.startswith("safecode/")
    assert outcome.pull_request.pr_number == _PR_NUMBER
    ref_calls = [call for call in calls if call.endswith("/git/refs")]
    pr_calls = [call for call in calls if call.endswith("/pulls")]
    assert len(ref_calls) == 1
    assert len(pr_calls) == 1

    audit = EnterpriseAuditChain(project_root_for_sac(sac_root))
    kinds = {event.type for event in audit.iter_events()}
    assert AuditEventKind.tool_call_executed.value in kinds
    rendered = branch_record.model_dump_json() + pr_record.model_dump_json()
    assert _TOKEN_RE.search(rendered) is None
    assert_output_safe(rendered, context="branch and PR tool records")


def test_protected_branch_push_audited_and_blocked(tmp_path):
    sac_root = tmp_path / ".sac"
    protected_spec = _branch_spec(branch_name="main")
    request = ApprovalRequest(
        request_id=_BRANCH_REQUEST_ID,
        run_id=_RUN_ID,
        tenant_id=_TENANT,
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
    transport = _recorded_transport(calls=calls)

    record = push_branch_governed(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=protected_spec,
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        branch_push_request_id=_BRANCH_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )

    assert record.outcome == "blocked"
    assert calls == []
    audit = EnterpriseAuditChain(project_root_for_sac(sac_root))
    assert any(
        event.type == AuditEventKind.policy_block.value
        and event.metadata.get("branch_name") == "main"
        for event in audit.iter_events()
    )


def test_branch_replay_after_consume_fails_closed(tmp_path):
    sac_root = tmp_path / ".sac"
    _approve_branch_push(sac_root)
    transport = _recorded_transport()

    first = push_branch_governed(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=_branch_spec(),
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        branch_push_request_id=_BRANCH_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )
    assert first.outcome == "ok"

    second = push_branch_governed(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=_branch_spec(),
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        branch_push_request_id=_BRANCH_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )
    assert second.outcome == "blocked"
