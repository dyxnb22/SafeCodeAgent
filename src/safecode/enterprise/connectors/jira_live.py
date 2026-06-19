"""Live Jira issue connector and governed comment writer (v2.4.4)."""

from __future__ import annotations

import base64
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
from safecode.enterprise.approvals.store import Action, consume_approved_request
from safecode.enterprise.audit.chain import EnterpriseAuditChain
from safecode.enterprise.audit.events import AuditEventKind
from safecode.enterprise.connectors.issue import IssueConnectorError, _from_jira_json
from safecode.enterprise.connectors.models import IssueEvidence
from safecode.enterprise.trace.events import TraceEventType
from safecode.enterprise.trace.session import emit_standalone_trace, project_root_for_sac
from safecode.enterprise.workflow.exceptions import WorkflowError
from safecode.enterprise.workflow.state import ApprovalDecision, ApprovalDecisionInputs, ToolCallRecord

_JIRA_TOKEN_RE = re.compile(r"ATATT[A-Za-z0-9_-]{20,}")
_MAX_RESPONSE_BYTES = 1_048_576
MAX_COMMENT_BODY_CHARS = 32_768


class IssueLiveConnectorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["live"] = "live"
    issue_key: str
    api_base_url: str = "https://example.atlassian.net"


class IssueCommentWriteSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["fixture", "live"] = "fixture"
    output_path: str | None = None
    issue_key: str | None = None
    api_base_url: str = "https://example.atlassian.net"


class IssueCommentWriteOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment_id: str
    comment_url: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def redact_jira_text(text: str) -> str:
    cleaned = redact_secrets(text)
    return _JIRA_TOKEN_RE.sub("[REDACTED_TOKEN]", cleaned)


def comment_body_digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def comment_approval_target(*, issue_key: str, body: str) -> dict[str, str]:
    redacted = redact_secrets(body)[:MAX_COMMENT_BODY_CHARS]
    target = {
        "issue_key": issue_key.strip(),
        "body_digest": comment_body_digest(redacted),
    }
    return dict(sorted(target.items()))


def body_contains_unredacted_secrets(body: str) -> bool:
    if redact_secrets(body) != body:
        return True
    return _JIRA_TOKEN_RE.search(body) is not None


def _validate_live_issue_key(issue_key: str) -> str:
    key = issue_key.strip()
    if not key:
        raise IssueConnectorError("issue_key is required for live Jira fetch")
    return key


def _validate_live_write_spec(spec: IssueCommentWriteSpec) -> str:
    issue_key = (spec.issue_key or "").strip()
    if not issue_key:
        raise IssueConnectorError("issue_key is required for live Jira comment write")
    return issue_key


def _basic_auth_header(email: str, api_token: SecretStr) -> str:
    payload = f"{email}:{api_token.get_secret_value()}".encode("utf-8")
    return "Basic " + base64.b64encode(payload).decode("ascii")


def _validate_live_response(response: httpx.Response) -> None:
    if response.status_code in {301, 302, 303, 307, 308}:
        raise IssueConnectorError("redirect responses are not allowed for live Jira access")
    if response.status_code == 429:
        raise IssueConnectorError("Jira rate limit exhausted")
    if len(response.content) > _MAX_RESPONSE_BYTES:
        raise IssueConnectorError("Jira response exceeds size limit")


def _raise_for_status(response: httpx.Response, *, context: str) -> None:
    _validate_live_response(response)
    if response.status_code >= 400:
        detail = redact_jira_text(response.text[:512])
        if response.status_code in {401, 403}:
            raise IssueConnectorError(f"{context}: Jira access denied")
        if response.status_code == 404:
            raise IssueConnectorError(f"{context}: issue not found")
        raise IssueConnectorError(f"{context} failed ({response.status_code}): {detail}")


@dataclass
class JiraIssueClient:
    """Fetch Jira issues using recorded or live HTTP transport."""

    _issue_key: str
    _email: str
    _api_token: SecretStr
    _api_base_url: str = "https://example.atlassian.net"
    _transport: httpx.BaseTransport | None = field(default=None, repr=False)
    _http_client: httpx.Client | None = field(default=None, repr=False)

    @classmethod
    def from_spec(
        cls,
        spec: IssueLiveConnectorSpec,
        *,
        email: str,
        api_token: SecretStr,
        transport: httpx.BaseTransport | None = None,
    ) -> JiraIssueClient:
        issue_key = _validate_live_issue_key(spec.issue_key)
        return cls(
            _issue_key=issue_key,
            _email=email.strip(),
            _api_token=api_token,
            _api_base_url=spec.api_base_url.rstrip("/"),
            _transport=transport,
        )

    def __repr__(self) -> str:
        return (
            "JiraIssueClient("
            f"issue_key={self._issue_key!r}, "
            f"email={self._email!r}, "
            "api_token=SecretStr('**********'))"
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
            "Authorization": _basic_auth_header(self._email, self._api_token),
            "Accept": "application/json",
        }

    def fetch(self) -> IssueEvidence:
        client = self._http()
        path = f"/rest/api/3/issue/{self._issue_key}"
        response = client.get(path, headers=self._auth_headers())
        _raise_for_status(response, context="issue fetch")
        try:
            payload = response.json()
        except ValueError as exc:
            raise IssueConnectorError("malformed Jira issue response") from exc
        if not isinstance(payload, dict):
            raise IssueConnectorError("malformed Jira issue response")
        return _from_jira_json(payload)


@dataclass
class JiraCommentClient:
    """Post Jira issue comments using recorded or live HTTP transport."""

    _issue_key: str
    _email: str
    _api_token: SecretStr
    _api_base_url: str = "https://example.atlassian.net"
    _transport: httpx.BaseTransport | None = field(default=None, repr=False)
    _http_client: httpx.Client | None = field(default=None, repr=False)

    @classmethod
    def from_spec(
        cls,
        spec: IssueCommentWriteSpec,
        *,
        email: str,
        api_token: SecretStr,
        transport: httpx.BaseTransport | None = None,
    ) -> JiraCommentClient:
        issue_key = _validate_live_write_spec(spec)
        return cls(
            _issue_key=issue_key,
            _email=email.strip(),
            _api_token=api_token,
            _api_base_url=spec.api_base_url.rstrip("/"),
            _transport=transport,
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
            "Authorization": _basic_auth_header(self._email, self._api_token),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def post_comment(self, *, body: str) -> IssueCommentWriteOutcome:
        if not body.strip():
            raise IssueConnectorError("comment body must not be empty")
        client = self._http()
        path = f"/rest/api/3/issue/{self._issue_key}/comment"
        response = client.post(path, headers=self._auth_headers(), json={"body": body})
        _raise_for_status(response, context="issue comment write")
        try:
            payload = response.json()
        except ValueError as exc:
            raise IssueConnectorError("malformed Jira comment response") from exc
        if not isinstance(payload, dict) or payload.get("id") is None:
            raise IssueConnectorError("malformed Jira comment response")
        comment_id = str(payload["id"])
        comment_url = str(payload.get("self") or "")
        return IssueCommentWriteOutcome(comment_id=comment_id, comment_url=comment_url)


def fetch_issue_live(
    spec: IssueLiveConnectorSpec,
    *,
    email: str,
    api_token: SecretStr,
    transport: httpx.BaseTransport | None = None,
) -> IssueEvidence:
    if not email.strip():
        raise IssueConnectorError("email is required for live Jira fetch")
    client = JiraIssueClient.from_spec(
        spec,
        email=email,
        api_token=api_token,
        transport=transport,
    )
    return client.fetch()


def _blocked_record(
    *,
    call_id: str,
    run_id: str,
    node_name: str,
    spec: IssueCommentWriteSpec,
    redacted_body: str,
    started: str,
    policy_snapshot_id: str,
    reason: str,
) -> ToolCallRecord:
    return ToolCallRecord(
        call_id=call_id,
        run_id=run_id,
        node_name=node_name,
        tool_name="jira_write",
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


def post_issue_comment(
    *,
    sac_root: Path,
    run_id: str,
    node_name: str,
    spec: IssueCommentWriteSpec,
    body: str,
    approved: bool,
    actor_id: str,
    tenant_id: str = "local",
    policy_snapshot_id: str = "snapshot-local",
    request_id: str | None = None,
    email: str | None = None,
    api_token: SecretStr | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ToolCallRecord:
    """Write a Jira comment offline or execute a governed live write."""
    redacted_body = redact_secrets(body)[:MAX_COMMENT_BODY_CHARS]
    call_id = f"tool-{uuid.uuid4().hex[:12]}"
    started = _utc_now()
    decision = ApprovalDecision(
        decision="GATE" if spec.mode == "live" else "AUTO",
        reason="fixture write" if spec.mode == "fixture" else "live jira write",
        policy_snapshot_id=policy_snapshot_id,
        inputs=ApprovalDecisionInputs(policy_value="GATE", rbac_value="GATE", tool_spec_value="GATE"),
    )
    record = ToolCallRecord(
        call_id=call_id,
        run_id=run_id,
        node_name=node_name,
        tool_name="jira_write",
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
                payload={"tool_name": "jira_write", "mode": "live", "reason": "secret_in_body"},
            )
            return record

        issue_key = _validate_live_write_spec(spec)
        target = comment_approval_target(issue_key=issue_key, body=body)
        if email is None or api_token is None:
            record = _blocked_record(
                call_id=call_id,
                run_id=run_id,
                node_name=node_name,
                spec=spec,
                redacted_body=redacted_body,
                started=started,
                policy_snapshot_id=policy_snapshot_id,
                reason="email and api_token are required for governed live write",
            )
            emit_standalone_trace(
                sac_root,
                run_id=run_id,
                tenant_id=tenant_id,
                event_type=TraceEventType.tool_blocked,
                node_id=node_name,
                actor_id=actor_id,
                policy_snapshot_id=policy_snapshot_id,
                payload={"tool_name": "jira_write", "mode": "live", "reason": "missing_credentials"},
            )
            return record

        try:
            grant = consume_approved_request(
                sac_root,
                run_id,
                request_id,
                tenant_id=tenant_id,
                action=Action.issue_comment,
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
                payload={"tool_name": "jira_write", "mode": "live", "reason": "grant_denied"},
            )
            return record

        record.grant_id = grant.grant_id
        try:
            client = JiraCommentClient.from_spec(
                spec,
                email=email,
                api_token=api_token,
                transport=transport,
            )
            outcome = client.post_comment(body=redacted_body)
        except IssueConnectorError as exc:
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
                payload={"tool_name": "jira_write", "mode": "live", "reason": "transport_error"},
            )
            return record

        audit = EnterpriseAuditChain(project_root_for_sac(sac_root))
        audit.emit(
            AuditEventKind.tool_call_executed,
            run_id=run_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
            payload={
                "tool_name": "jira_write",
                "mode": "live",
                "comment_id": outcome.comment_id,
                "issue_key": issue_key,
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
                "tool_name": "jira_write",
                "mode": "live",
                "comment_id": outcome.comment_id,
                "grant_id": grant.grant_id,
            },
        )
        return record

    if spec.mode == "live" and not approved:
        record.outcome = "blocked"
        record.ended_at = _utc_now()
        emit_standalone_trace(
            sac_root,
            run_id=run_id,
            tenant_id=tenant_id,
            event_type=TraceEventType.tool_blocked,
            node_id=node_name,
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            payload={"tool_name": "jira_write", "mode": "live"},
        )
        return record

    if spec.mode == "fixture":
        if not spec.output_path:
            raise ValueError("output_path is required for fixture mode")
        path = Path(spec.output_path)
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
            payload={"tool_name": "jira_write", "mode": "fixture", "path": str(path)},
        )
        return record

    record.outcome = "ok"
    record.output_excerpt = "live write recorded (offline default)"
    record.ended_at = _utc_now()
    emit_standalone_trace(
        sac_root,
        run_id=run_id,
        tenant_id=tenant_id,
        event_type=TraceEventType.tool_executed,
        node_id=node_name,
        actor_id=actor_id,
        policy_snapshot_id=policy_snapshot_id,
        payload={"tool_name": "jira_write", "mode": "live", "actor": actor_id},
    )
    return record
