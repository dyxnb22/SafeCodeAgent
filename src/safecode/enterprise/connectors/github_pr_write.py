"""GitHub PR comment writer (fixture-first, governed live mode v2.2.3-T1)."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

from safecode.context.redactor import redact_secrets
from safecode.enterprise.approvals.digest import merge_proposal_sha256
from safecode.enterprise.approvals.store import (
    Action,
    consume_approved_request,
)
from safecode.enterprise.workflow.exceptions import WorkflowError
from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.connectors.github_app import assert_output_safe
from safecode.enterprise.connectors.github_pr import ConnectorError, redact_connector_text
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.trace.session import emit_standalone_trace, project_root_for_sac
from safecode.enterprise.workflow.state import ApprovalDecision, ApprovalDecisionInputs, ToolCallRecord

_GH_TOKEN_RE = re.compile(r"gh[psur]_[A-Za-z0-9]{20,}")
MAX_COMMENT_BODY_CHARS = 65_536


def _resolve_fixture_output_path(output_path: str, project_root: Path) -> Path:
    resolved = (project_root / output_path).resolve()
    root_resolved = project_root.resolve()
    if root_resolved not in resolved.parents and resolved != root_resolved:
        raise ValueError(f"fixture output_path escapes project root: {output_path!r}")
    return resolved


class PRCommentWriteSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["fixture", "live"] = "fixture"
    output_path: str | None = None
    owner: str | None = None
    repo: str | None = None
    pr_number: int | None = None
    api_base_url: str = "https://api.github.com"


class PRCommentWriteOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment_id: str
    comment_url: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def comment_body_digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def comment_approval_target(
    *,
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
) -> dict[str, str]:
    redacted = redact_secrets(body)[:MAX_COMMENT_BODY_CHARS]
    target = {
        "owner": owner.strip(),
        "repo": repo.strip(),
        "pr_number": str(pr_number),
        "body_digest": comment_body_digest(redacted),
    }
    return dict(sorted(target.items()))


def body_contains_unredacted_secrets(body: str) -> bool:
    if redact_secrets(body) != body:
        return True
    return _GH_TOKEN_RE.search(body) is not None


def _validate_live_spec(spec: PRCommentWriteSpec) -> tuple[str, str, int]:
    owner = (spec.owner or "").strip()
    repo = (spec.repo or "").strip()
    pr_number = spec.pr_number or 0
    if not owner or not repo:
        raise ConnectorError("owner and repo are required for live PR comment write")
    if pr_number <= 0:
        raise ConnectorError("pr_number is required for live PR comment write")
    return owner, repo, pr_number


@dataclass
class GitHubPRCommentClient:
    """Post pull request comments using recorded or live HTTP transport."""

    _owner: str
    _repo: str
    _access_token: SecretStr
    _api_base_url: str = "https://api.github.com"
    _transport: httpx.BaseTransport | None = field(default=None, repr=False)
    _http_client: httpx.Client | None = field(default=None, repr=False)

    @classmethod
    def from_spec(
        cls,
        spec: PRCommentWriteSpec,
        *,
        access_token: SecretStr,
        transport: httpx.BaseTransport | None = None,
    ) -> GitHubPRCommentClient:
        owner, repo, _ = _validate_live_spec(spec)
        return cls(
            _owner=owner,
            _repo=repo,
            _access_token=access_token,
            _api_base_url=spec.api_base_url.rstrip("/"),
            _transport=transport,
        )

    def __repr__(self) -> str:
        return (
            "GitHubPRCommentClient("
            f"owner={self._owner!r}, "
            f"repo={self._repo!r}, "
            "access_token=SecretStr('**********'))"
        )

    def _http(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(
                transport=self._transport,
                base_url=self._api_base_url,
                timeout=30.0,
                follow_redirects=False,
            )
        return self._http_client

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token.get_secret_value()}",
            "Accept": "application/vnd.github+json",
        }

    def post_comment(self, *, pr_number: int, body: str) -> PRCommentWriteOutcome:
        if pr_number <= 0:
            raise ConnectorError("pr_number must be positive")
        if not body.strip():
            raise ConnectorError("comment body must not be empty")
        client = self._http()
        path = f"/repos/{self._owner}/{self._repo}/issues/{pr_number}/comments"
        response = client.post(path, headers=self._auth_headers(), json={"body": body})
        if response.status_code in {301, 302, 303, 307, 308}:
            raise ConnectorError("redirect responses are not allowed for live PR comment write")
        if response.status_code == 429:
            raise ConnectorError("GitHub rate limit exhausted")
        if response.status_code >= 400:
            detail = redact_connector_text(redact_secrets(response.text[:512]))
            raise ConnectorError(f"PR comment write failed ({response.status_code}): {detail}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError("malformed GitHub comment response") from exc
        if not isinstance(payload, dict) or payload.get("id") is None:
            raise ConnectorError("malformed GitHub comment response")
        comment_id = str(payload["id"])
        comment_url = str(payload.get("html_url") or "")
        rendered = f"comment_id={comment_id} url={comment_url}"
        assert_output_safe(rendered, context="PR comment write outcome")
        return PRCommentWriteOutcome(comment_id=comment_id, comment_url=comment_url)


def _blocked_record(
    *,
    call_id: str,
    run_id: str,
    node_name: str,
    spec: PRCommentWriteSpec,
    redacted_body: str,
    started: str,
    policy_snapshot_id: str,
    reason: str,
) -> ToolCallRecord:
    return ToolCallRecord(
        call_id=call_id,
        run_id=run_id,
        node_name=node_name,
        tool_name="github_write",
        tool_category="write_network" if spec.mode == "live" else "write_local",
        inputs_redacted={"mode": spec.mode, "body": redacted_body[:512], "reason": reason[:256]},
        decision=ApprovalDecision(
            decision="GATE",
            reason=reason,
            policy_snapshot_id=policy_snapshot_id,
            inputs=ApprovalDecisionInputs(policy_value="GATE", rbac_value="GATE", tool_spec_value="GATE"),
        ),
        outcome="blocked",
        started_at=started,
        ended_at=_utc_now(),
    )


def post_pr_comment(
    *,
    sac_root: Path,
    run_id: str,
    node_name: str,
    spec: PRCommentWriteSpec,
    body: str,
    approved: bool,
    actor_id: str,
    tenant_id: str = "local",
    policy_snapshot_id: str = "snapshot-local",
    request_id: str | None = None,
    proposal_ref: str | None = None,
    access_token: SecretStr | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ToolCallRecord:
    """Write a PR comment offline or execute a governed live write."""
    redacted_body = redact_secrets(body)[:MAX_COMMENT_BODY_CHARS]
    call_id = f"tool-{uuid.uuid4().hex[:12]}"
    started = _utc_now()
    decision = ApprovalDecision(
        decision="GATE" if spec.mode == "live" else "AUTO",
        reason="fixture write" if spec.mode == "fixture" else "live github write",
        policy_snapshot_id=policy_snapshot_id,
        inputs=ApprovalDecisionInputs(policy_value="GATE", rbac_value="GATE", tool_spec_value="GATE"),
    )
    record = ToolCallRecord(
        call_id=call_id,
        run_id=run_id,
        node_name=node_name,
        tool_name="github_write",
        tool_category="write_network" if spec.mode == "live" else "write_local",
        inputs_redacted={"mode": spec.mode, "body": redacted_body[:512]},
        decision=decision,
        started_at=started,
    )

    if spec.mode == "live" and request_id is not None:
        if body_contains_unredacted_secrets(body):
            record = _blocked_record(
                call_id=call_id,
                run_id=run_id,
                node_name=node_name,
                spec=spec,
                redacted_body=redacted_body,
                started=started,
                policy_snapshot_id=policy_snapshot_id,
                reason="comment body contains secret material",
            )
            emit_standalone_trace(
                sac_root,
                run_id=run_id,
                tenant_id=tenant_id,
                event_type=TraceEventType.tool_blocked,
                node_id=node_name,
                actor_id=actor_id,
                policy_snapshot_id=policy_snapshot_id,
                payload={"tool_name": "github_write", "mode": "live", "reason": "secret_in_body"},
            )
            return record

        owner, repo, pr_number = _validate_live_spec(spec)
        target = comment_approval_target(owner=owner, repo=repo, pr_number=pr_number, body=body)
        if proposal_ref:
            target = merge_proposal_sha256(target, proposal_ref)
        if access_token is None:
            record = _blocked_record(
                call_id=call_id,
                run_id=run_id,
                node_name=node_name,
                spec=spec,
                redacted_body=redacted_body,
                started=started,
                policy_snapshot_id=policy_snapshot_id,
                reason="access_token is required for governed live write",
            )
            emit_standalone_trace(
                sac_root,
                run_id=run_id,
                tenant_id=tenant_id,
                event_type=TraceEventType.tool_blocked,
                node_id=node_name,
                actor_id=actor_id,
                policy_snapshot_id=policy_snapshot_id,
                payload={"tool_name": "github_write", "mode": "live", "reason": "missing_token"},
            )
            return record

        try:
            grant = consume_approved_request(
                sac_root,
                run_id,
                request_id,
                tenant_id=tenant_id,
                action=Action.github_write_comment,
                policy_snapshot_id=policy_snapshot_id,
                target=target,
            )
        except (PermissionError, WorkflowError) as exc:
            record = _blocked_record(
                call_id=call_id,
                run_id=run_id,
                node_name=node_name,
                spec=spec,
                redacted_body=redacted_body,
                started=started,
                policy_snapshot_id=policy_snapshot_id,
                reason=str(exc),
            )
            emit_standalone_trace(
                sac_root,
                run_id=run_id,
                tenant_id=tenant_id,
                event_type=TraceEventType.tool_blocked,
                node_id=node_name,
                actor_id=actor_id,
                policy_snapshot_id=policy_snapshot_id,
                payload={"tool_name": "github_write", "mode": "live", "reason": "grant_denied"},
            )
            return record

        record.grant_id = grant.grant_id
        try:
            client = GitHubPRCommentClient.from_spec(
                spec,
                access_token=access_token,
                transport=transport,
            )
            outcome = client.post_comment(pr_number=pr_number, body=redacted_body)
        except ConnectorError as exc:
            record.outcome = "error"
            record.output_excerpt = redact_secrets(str(exc))[:256]
            record.ended_at = _utc_now()
            emit_standalone_trace(
                sac_root,
                run_id=run_id,
                tenant_id=tenant_id,
                event_type=TraceEventType.tool_blocked,
                node_id=node_name,
                actor_id=actor_id,
                policy_snapshot_id=policy_snapshot_id,
                payload={"tool_name": "github_write", "mode": "live", "reason": "transport_error"},
            )
            return record

        audit = EnterpriseAuditChain(project_root_for_sac(sac_root))
        audit.emit(
            AuditEventKind.tool_call_executed,
            run_id=run_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
            payload={
                "tool_name": "github_write",
                "mode": "live",
                "comment_id": outcome.comment_id,
                "owner": owner,
                "repo": repo,
                "pr_number": str(pr_number),
            },
        )
        record.outcome = "ok"
        record.output_excerpt = f"comment_id={outcome.comment_id}"[:256]
        record.ended_at = _utc_now()
        emit_standalone_trace(
            sac_root,
            run_id=run_id,
            tenant_id=tenant_id,
            event_type=TraceEventType.tool_executed,
            node_id=node_name,
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            payload={
                "tool_name": "github_write",
                "mode": "live",
                "comment_id": outcome.comment_id,
                "grant_id": grant.grant_id,
            },
        )
        return record

    if spec.mode == "live":
        record.outcome = "blocked"
        record.output_excerpt = "live write requires a bound single-use approval grant"
        record.ended_at = _utc_now()
        emit_standalone_trace(
            sac_root,
            run_id=run_id,
            tenant_id=tenant_id,
            event_type=TraceEventType.tool_blocked,
            node_id=node_name,
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            payload={
                "tool_name": "github_write",
                "mode": "live",
                "reason": "missing_bound_grant",
            },
        )
        return record

    if spec.mode == "fixture":
        if not spec.output_path:
            raise ValueError("output_path is required for fixture mode")
        project_root = project_root_for_sac(sac_root)
        path = _resolve_fixture_output_path(spec.output_path, project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(redacted_body, encoding="utf-8")
        record.outcome = "ok"
        record.output_excerpt = redacted_body[:256]
        record.ended_at = _utc_now()
        emit_standalone_trace(
            sac_root,
            run_id=run_id,
            tenant_id=tenant_id,
            event_type=TraceEventType.tool_executed,
            node_id=node_name,
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            payload={"tool_name": "github_write", "mode": "fixture", "path": str(path)},
        )
        return record

    raise ValueError(f"unsupported PR comment write mode: {spec.mode}")
