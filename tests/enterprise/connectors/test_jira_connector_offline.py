"""Offline Jira connector tests (v2.4.4)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from safecode.enterprise.approvals.store import (
    Action,
    ApprovalRequest,
    decide_request,
    save_request,
)
from safecode.enterprise.connectors.issue import IssueConnectorError, IssueConnectorSpec, fetch_issue
from safecode.enterprise.connectors.jira_live import (
    IssueCommentWriteSpec,
    IssueLiveConnectorSpec,
    comment_approval_target,
    fetch_issue_live,
    post_issue_comment,
)
from safecode.enterprise.workflow.types import RiskTier

_ISSUE_KEY = "SEC-101"
_EMAIL = "agent@example.com"
_TOKEN = SecretStr("ATATT3xFfGF0recorded_jira_api_token_for_tests")
_BASE_URL = "https://example.atlassian.net"
_RUN_ID = "run-jiraoffline01"
_TENANT = "tenant-a"
_POLICY = "snapshot-test"
_REQUEST_ID = "approval-run-jiraoffline01"


def _jira_issue_payload() -> dict:
    return {
        "key": _ISSUE_KEY,
        "fields": {
            "summary": "SQL injection in login",
            "description": "User input reaches SQL without parameterization.",
            "labels": ["security", "bug"],
            "priority": {"name": "high"},
            "reporter": {"emailAddress": "reporter@example.com"},
        },
    }


def _recorded_read_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and f"/issue/{_ISSUE_KEY}" in request.url.path:
            return httpx.Response(200, json=_jira_issue_payload())
        return httpx.Response(404, json={"errorMessages": ["Issue not found"]})

    return httpx.MockTransport(handler)


def _recorded_write_transport(*, calls: list[str] | None = None) -> httpx.MockTransport:
    observed: list[str] = calls if calls is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(f"{request.method} {request.url.path}")
        if request.method == "POST" and request.url.path.endswith("/comment"):
            return httpx.Response(201, json={"id": "10001", "self": f"{_BASE_URL}/comment/10001"})
        return httpx.Response(404, json={"errorMessages": ["Not found"]})

    return httpx.MockTransport(handler)


def test_fixture_fetch_issue_still_default_offline_path(tmp_path: Path):
    markdown = tmp_path / "ticket.md"
    markdown.write_text("# SQL injection in login\n\nSeverity: high\nLabels: security, bug\n", encoding="utf-8")
    evidence = fetch_issue(
        IssueConnectorSpec(source_kind="markdown", source_path=markdown.name, project_root=str(tmp_path))
    )
    assert evidence.title == "SQL injection in login"
    assert evidence.severity == "high"
    assert "security" in evidence.labels


def test_live_fetch_requires_credentials():
    with pytest.raises(IssueConnectorError, match="email and api_token"):
        fetch_issue(
            IssueConnectorSpec(mode="live", issue_key=_ISSUE_KEY, api_base_url=_BASE_URL),
        )


def test_live_fetch_uses_recorded_transport():
    evidence = fetch_issue_live(
        IssueLiveConnectorSpec(issue_key=_ISSUE_KEY, api_base_url=_BASE_URL),
        email=_EMAIL,
        api_token=_TOKEN,
        transport=_recorded_read_transport(),
    )
    assert evidence.issue_id == _ISSUE_KEY
    assert evidence.severity == "high"
    assert "security" in evidence.labels


def test_live_fetch_denied_without_grant_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"errorMessages": ["Forbidden"]})

    with pytest.raises(IssueConnectorError, match="access denied"):
        fetch_issue_live(
            IssueLiveConnectorSpec(issue_key=_ISSUE_KEY, api_base_url=_BASE_URL),
            email=_EMAIL,
            api_token=_TOKEN,
            transport=httpx.MockTransport(handler),
        )


def _approve_comment_request(sac_root: Path, *, body: str) -> None:
    target = comment_approval_target(issue_key=_ISSUE_KEY, body=body)
    request = ApprovalRequest(
        request_id=_REQUEST_ID,
        run_id=_RUN_ID,
        tenant_id=_TENANT,
        action=Action.issue_comment,
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
        _REQUEST_ID,
        decision="approved",
        decision_actor="user:reviewer",
    )


def test_live_write_without_approval_is_blocked(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    record = post_issue_comment(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=IssueCommentWriteSpec(mode="live", issue_key=_ISSUE_KEY, api_base_url=_BASE_URL),
        body="Planning update",
        approved=False,
        actor_id="user:test",
    )
    assert record.outcome == "blocked"
    assert record.tool_name == "jira_write"


def test_fixture_write_persists_redacted_body(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    out = tmp_path / "comment.md"
    body = "Rotate password=super_secret_value_for_test"
    record = post_issue_comment(
        sac_root=sac_root,
        run_id="run-jiraoffline02",
        node_name="finalize",
        spec=IssueCommentWriteSpec(mode="fixture", output_path=str(out)),
        body=body,
        approved=False,
        actor_id="user:test",
    )
    assert record.outcome == "ok"
    written = out.read_text(encoding="utf-8")
    assert "ATATT" not in written
    assert "super_secret" not in written


def test_governed_live_write_posts_once(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    body = "Secure planning draft attached."
    _approve_comment_request(sac_root, body=body)
    calls: list[str] = []
    transport = _recorded_write_transport(calls=calls)
    record = post_issue_comment(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=IssueCommentWriteSpec(mode="live", issue_key=_ISSUE_KEY, api_base_url=_BASE_URL),
        body=body,
        approved=False,
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        request_id=_REQUEST_ID,
        email=_EMAIL,
        api_token=_TOKEN,
        transport=transport,
    )
    assert record.outcome == "ok"
    assert record.grant_id is not None
    assert len(calls) == 1
    assert calls[0].endswith(f"/issue/{_ISSUE_KEY}/comment")


def test_no_grant_never_writes(tmp_path: Path):
    sac_root = tmp_path / ".sac"
    calls: list[str] = []
    transport = _recorded_write_transport(calls=calls)
    record = post_issue_comment(
        sac_root=sac_root,
        run_id=_RUN_ID,
        node_name="finalize",
        spec=IssueCommentWriteSpec(mode="live", issue_key=_ISSUE_KEY, api_base_url=_BASE_URL),
        body="blocked",
        approved=False,
        actor_id="user:approver",
        tenant_id=_TENANT,
        policy_snapshot_id=_POLICY,
        request_id=_REQUEST_ID,
        email=_EMAIL,
        api_token=_TOKEN,
        transport=transport,
    )
    assert record.outcome == "blocked"
    assert calls == []


@pytest.mark.live_jira
def test_live_jira_marker_is_opt_in() -> None:
    """Opt-in lane marker; default CI excludes this module via -m 'not live_jira'."""
    assert True
