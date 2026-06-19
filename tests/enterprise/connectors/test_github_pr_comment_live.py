"""Governed live GitHub PR comment write tests (v2.2.3-T1)."""

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
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.connectors.github_app import assert_output_safe
from safecode.enterprise.connectors.github_pr_write import (
    PRCommentWriteSpec,
    comment_approval_target as build_target,
    post_pr_comment,
)
from safecode.enterprise.trace.session import project_root_for_sac
from safecode.enterprise.workflow.types import RiskTier
from safecode.enterprise.audit.chain import EnterpriseAuditChain

_OWNER = "acme"
_REPO = "webapp"
_PR_NUMBER = 42
_RUN_ID = "run-commentlive01"
_TENANT = "tenant-a"
_POLICY = "snapshot-test"
_REQUEST_ID = "approval-run-commentlive01"
_ACCESS_TOKEN = SecretStr("ghs_recorded_installation_token_for_comment_write")
_TOKEN_RE = re.compile(r"gh[ps]_[A-Za-z0-9]{20,}")
_COMMENT_BODY = "Please rotate credentials before merge."
_COMMENT_ID = "987654321"


def _live_spec(**overrides: object) -> PRCommentWriteSpec:
    base = {
        "mode": "live",
        "owner": _OWNER,
        "repo": _REPO,
        "pr_number": _PR_NUMBER,
        "api_base_url": "https://api.github.com",
    }
    base.update(overrides)
    return PRCommentWriteSpec.model_validate(base)


def _recorded_transport(*, calls: list[str] | None = None) -> httpx.MockTransport:
    observed: list[str] = calls if calls is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(f"{request.method} {request.url.path}")
        if request.method == "POST" and request.url.path.endswith("/comments"):
            return httpx.Response(
                201,
                json={
                    "id": int(_COMMENT_ID),
                    "html_url": f"https://github.com/{_OWNER}/{_REPO}/issues/{_PR_NUMBER}#issuecomment-{_COMMENT_ID}",
                    "body": _COMMENT_BODY,
                },
            )
        return httpx.Response(404, json={"message": "Not Found"})

    handler.observed = observed  # type: ignore[attr-defined]
    return httpx.MockTransport(handler)


def _approve_comment_request(
    sac_root,
    *,
    body: str = _COMMENT_BODY,
    tenant_id: str = _TENANT,
    request_id: str = _REQUEST_ID,
) -> dict[str, str]:
    target = build_target(
        owner=_OWNER,
        repo=_REPO,
        pr_number=_PR_NUMBER,
        body=body,
    )
    request = ApprovalRequest(
        request_id=request_id,
        run_id=_RUN_ID,
        tenant_id=tenant_id,
        action=Action.github_write_comment,
        risk_tier=RiskTier.medium,
        requested_by_node="finalize",
        requesting_actor="user:approver",
        target=target,
        preview=body[:256],
        policy_snapshot_id=_POLICY,
        created_at="2026-06-19T00:00:00+00:00",
    )
    save_request(sac_root, request)
    decide_request(
        sac_root,
        _RUN_ID,
        request_id,
        decision="approved",
        decision_actor="user:reviewer",
    )
    return target


def test_approved_live_write_posts_once_with_recorded_transport(tmp_path):
    sac_root = tmp_path / ".sac"
    _approve_comment_request(sac_root)
    calls: list[str] = []
    transport = _recorded_transport(calls=calls)

    record = post_pr_comment(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=_live_spec(),
        body=_COMMENT_BODY,
        approved=False,
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        request_id=_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )

    assert record.outcome == "ok"
    assert record.grant_id is not None
    assert f"comment_id={_COMMENT_ID}" in record.output_excerpt
    assert len(calls) == 1
    assert calls[0].endswith(f"/repos/{_OWNER}/{_REPO}/issues/{_PR_NUMBER}/comments")

    audit = EnterpriseAuditChain(project_root_for_sac(sac_root))
    events = audit.iter_events()
    assert any(
        event.type == AuditEventKind.tool_call_executed.value
        and event.metadata.get("comment_id") == _COMMENT_ID
        for event in events
    )
    rendered = record.model_dump_json()
    assert _TOKEN_RE.search(rendered) is None
    assert_output_safe(rendered, context="PR comment tool record")


def test_no_grant_never_writes(tmp_path):
    sac_root = tmp_path / ".sac"
    calls: list[str] = []
    transport = _recorded_transport(calls=calls)

    record = post_pr_comment(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=_live_spec(),
        body=_COMMENT_BODY,
        approved=False,
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        request_id=_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )

    assert record.outcome == "blocked"
    assert calls == []


def test_legacy_approved_boolean_cannot_replace_a_bound_grant(tmp_path):
    sac_root = tmp_path / ".sac"
    calls: list[str] = []
    record = post_pr_comment(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=_live_spec(),
        body=_COMMENT_BODY,
        approved=True,
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        request_id=None,
        access_token=_ACCESS_TOKEN,
        transport=_recorded_transport(calls=calls),
    )
    assert record.outcome == "blocked"
    assert calls == []


def test_replay_after_consume_fails_closed(tmp_path):
    sac_root = tmp_path / ".sac"
    _approve_comment_request(sac_root)
    transport = _recorded_transport()

    first = post_pr_comment(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=_live_spec(),
        body=_COMMENT_BODY,
        approved=False,
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        request_id=_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )
    assert first.outcome == "ok"

    second = post_pr_comment(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=_live_spec(),
        body=_COMMENT_BODY,
        approved=False,
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        request_id=_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )
    assert second.outcome == "blocked"


def test_digest_change_fails_closed(tmp_path):
    sac_root = tmp_path / ".sac"
    _approve_comment_request(sac_root, body=_COMMENT_BODY)
    calls: list[str] = []
    transport = _recorded_transport(calls=calls)

    record = post_pr_comment(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=_live_spec(),
        body="Different comment body after approval",
        approved=False,
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        request_id=_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )

    assert record.outcome == "blocked"
    assert calls == []


def test_tenant_mismatch_fails_closed(tmp_path):
    sac_root = tmp_path / ".sac"
    _approve_comment_request(sac_root, tenant_id=_TENANT)
    calls: list[str] = []
    transport = _recorded_transport(calls=calls)

    record = post_pr_comment(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=_live_spec(),
        body=_COMMENT_BODY,
        approved=False,
        actor_id="user:approver",
        tenant_id="tenant-b",
        policy_snapshot_id=_POLICY,
        request_id=_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )

    assert record.outcome == "blocked"
    assert calls == []


def test_secret_in_body_fails_closed(tmp_path):
    sac_root = tmp_path / ".sac"
    secret_body = "Use token ghp_1234567890123456789012345678901234 in the request"
    _approve_comment_request(sac_root, body=secret_body)
    calls: list[str] = []
    transport = _recorded_transport(calls=calls)

    record = post_pr_comment(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=_live_spec(),
        body=secret_body,
        approved=False,
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        request_id=_REQUEST_ID,
        access_token=_ACCESS_TOKEN,
        transport=transport,
    )

    assert record.outcome == "blocked"
    assert calls == []
