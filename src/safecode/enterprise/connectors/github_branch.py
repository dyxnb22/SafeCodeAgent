"""GitHub branch push and PR create connectors (governed live mode v2.2.3-T2)."""

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

PROTECTED_BRANCHES: frozenset[str] = frozenset({"main", "master", "trunk"})
BRANCH_NAMESPACE_PREFIX = "safecode"
_SAFE_BRANCH = re.compile(r"^[a-zA-Z0-9._/-]{1,200}$")
MAX_PR_BODY_CHARS = 65_536


class BranchPushSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str
    repo: str
    base_branch: str
    branch_name: str
    commit_sha: str
    patch_digest: str
    api_base_url: str = "https://api.github.com"


class PRCreateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str
    repo: str
    head_branch: str
    base_branch: str
    title: str
    body: str
    api_base_url: str = "https://api.github.com"


class BranchPushOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_name: str
    ref_sha: str


class PRCreateOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pr_number: int
    pr_url: str = ""


class SecureChangeOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch: BranchPushOutcome
    pull_request: PRCreateOutcome


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def namespaced_branch_name(run_id: str, *, slug: str = "change") -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "-", run_id).strip("-")[:48] or "run"
    return f"{BRANCH_NAMESPACE_PREFIX}/{safe}/{slug}"


def is_protected_branch(branch_name: str) -> bool:
    normalized = branch_name.strip().lower()
    leaf = normalized.rsplit("/", 1)[-1]
    return leaf in PROTECTED_BRANCHES


def branch_push_target(spec: BranchPushSpec) -> dict[str, str]:
    target = {
        "owner": spec.owner.strip(),
        "repo": spec.repo.strip(),
        "branch_name": spec.branch_name.strip(),
        "base_branch": spec.base_branch.strip(),
        "commit_sha": spec.commit_sha.strip(),
        "patch_digest": spec.patch_digest.strip(),
    }
    return dict(sorted(target.items()))


def pr_create_target(spec: PRCreateSpec) -> dict[str, str]:
    redacted_body = redact_secrets(spec.body)[:MAX_PR_BODY_CHARS]
    target = {
        "owner": spec.owner.strip(),
        "repo": spec.repo.strip(),
        "head_branch": spec.head_branch.strip(),
        "base_branch": spec.base_branch.strip(),
        "title_digest": _digest(spec.title.strip()),
        "body_digest": _digest(redacted_body),
    }
    return dict(sorted(target.items()))


def _validate_branch_name(branch_name: str) -> None:
    if not branch_name or not _SAFE_BRANCH.match(branch_name):
        raise ConnectorError(f"invalid branch name: {branch_name!r}")
    if branch_name.startswith("-"):
        raise ConnectorError(f"branch name must not start with '-': {branch_name!r}")


def _validate_push_spec(spec: BranchPushSpec) -> None:
    if not spec.owner.strip() or not spec.repo.strip():
        raise ConnectorError("owner and repo are required for branch push")
    if not spec.commit_sha.strip():
        raise ConnectorError("commit_sha is required for branch push")
    if not spec.patch_digest.strip():
        raise ConnectorError("patch_digest is required for branch push")
    _validate_branch_name(spec.branch_name)
    if not spec.branch_name.startswith(f"{BRANCH_NAMESPACE_PREFIX}/"):
        raise ConnectorError("branch_name must use the safecode namespace prefix")
    if is_protected_branch(spec.branch_name):
        raise ConnectorError(f"protected branch push is not allowed: {spec.branch_name}")


@dataclass
class GitHubBranchClient:
    """Create branch refs and pull requests using recorded or live HTTP transport."""

    _owner: str
    _repo: str
    _access_token: SecretStr
    _api_base_url: str = "https://api.github.com"
    _transport: httpx.BaseTransport | None = field(default=None, repr=False)
    _http_client: httpx.Client | None = field(default=None, repr=False)

    @classmethod
    def from_owner_repo(
        cls,
        *,
        owner: str,
        repo: str,
        access_token: SecretStr,
        api_base_url: str = "https://api.github.com",
        transport: httpx.BaseTransport | None = None,
    ) -> GitHubBranchClient:
        if not owner.strip() or not repo.strip():
            raise ConnectorError("owner and repo are required")
        return cls(
            _owner=owner.strip(),
            _repo=repo.strip(),
            _access_token=access_token,
            _api_base_url=api_base_url.rstrip("/"),
            _transport=transport,
        )

    def __repr__(self) -> str:
        return (
            "GitHubBranchClient("
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

    def create_branch_ref(self, *, branch_name: str, commit_sha: str) -> BranchPushOutcome:
        client = self._http()
        path = f"/repos/{self._owner}/{self._repo}/git/refs"
        response = client.post(
            path,
            headers=self._auth_headers(),
            json={"ref": f"refs/heads/{branch_name}", "sha": commit_sha},
        )
        if response.status_code in {301, 302, 303, 307, 308}:
            raise ConnectorError("redirect responses are not allowed for branch push")
        if response.status_code == 429:
            raise ConnectorError("GitHub rate limit exhausted")
        if response.status_code >= 400:
            detail = redact_connector_text(redact_secrets(response.text[:512]))
            raise ConnectorError(f"branch push failed ({response.status_code}): {detail}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError("malformed GitHub branch response") from exc
        if not isinstance(payload, dict):
            raise ConnectorError("malformed GitHub branch response")
        object_payload = payload.get("object") or {}
        ref_sha = str(object_payload.get("sha") or commit_sha)
        rendered = f"branch={branch_name} sha={ref_sha}"
        assert_output_safe(rendered, context="branch push outcome")
        return BranchPushOutcome(branch_name=branch_name, ref_sha=ref_sha)

    def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
    ) -> PRCreateOutcome:
        client = self._http()
        path = f"/repos/{self._owner}/{self._repo}/pulls"
        response = client.post(
            path,
            headers=self._auth_headers(),
            json={
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
            },
        )
        if response.status_code in {301, 302, 303, 307, 308}:
            raise ConnectorError("redirect responses are not allowed for PR create")
        if response.status_code == 429:
            raise ConnectorError("GitHub rate limit exhausted")
        if response.status_code >= 400:
            detail = redact_connector_text(redact_secrets(response.text[:512]))
            raise ConnectorError(f"PR create failed ({response.status_code}): {detail}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError("malformed GitHub pull response") from exc
        if not isinstance(payload, dict) or payload.get("number") is None:
            raise ConnectorError("malformed GitHub pull response")
        pr_number = int(payload["number"])
        pr_url = str(payload.get("html_url") or "")
        rendered = f"pr_number={pr_number} url={pr_url}"
        assert_output_safe(rendered, context="PR create outcome")
        return PRCreateOutcome(pr_number=pr_number, pr_url=pr_url)


def _emit_protected_branch_block(
    *,
    sac_root: Path,
    run_id: str,
    tenant_id: str,
    actor_id: str,
    policy_snapshot_id: str,
    node_name: str,
    branch_name: str,
) -> None:
    audit = EnterpriseAuditChain(project_root_for_sac(sac_root))
    audit.emit(
        AuditEventKind.policy_block,
        run_id=run_id,
        actor_id=actor_id,
        tenant_id=tenant_id,
        status="blocked",
        message="protected branch push refused",
        payload={
            "tool_name": "github_branch_push",
            "branch_name": branch_name,
        },
    )
    emit_standalone_trace(
        sac_root,
        run_id=run_id,
        tenant_id=tenant_id,
        event_type=TraceEventType.tool_blocked,
        node_id=node_name,
        actor_id=actor_id,
        policy_snapshot_id=policy_snapshot_id,
        payload={
            "tool_name": "github_branch_push",
            "reason": "protected_branch",
            "branch_name": branch_name,
        },
    )


def push_branch_governed(
    *,
    sac_root: Path,
    run_id: str,
    node_name: str,
    spec: BranchPushSpec,
    actor_id: str,
    tenant_id: str,
    policy_snapshot_id: str,
    branch_push_request_id: str,
    access_token: SecretStr,
    transport: httpx.BaseTransport | None = None,
) -> ToolCallRecord:
    call_id = f"tool-{uuid.uuid4().hex[:12]}"
    started = _utc_now()
    record = ToolCallRecord(
        call_id=call_id,
        run_id=run_id,
        node_name=node_name,
        tool_name="github_branch_push",
        tool_category="write_network",
        inputs_redacted={
            "owner": spec.owner,
            "repo": spec.repo,
            "branch_name": spec.branch_name,
            "commit_sha": spec.commit_sha[:16],
        },
        decision=ApprovalDecision(
            decision="GATE",
            reason="governed branch push",
            policy_snapshot_id=policy_snapshot_id,
            inputs=ApprovalDecisionInputs(policy_value="GATE", rbac_value="GATE", tool_spec_value="GATE"),
        ),
        started_at=started,
    )

    if is_protected_branch(spec.branch_name):
        record.outcome = "blocked"
        record.output_excerpt = "protected branch push refused"
        record.ended_at = _utc_now()
        _emit_protected_branch_block(
            sac_root=sac_root,
            run_id=run_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            policy_snapshot_id=policy_snapshot_id,
            node_name=node_name,
            branch_name=spec.branch_name,
        )
        return record

    try:
        _validate_push_spec(spec)
    except ConnectorError as exc:
        record.outcome = "blocked"
        record.output_excerpt = redact_secrets(str(exc))[:256]
        record.ended_at = _utc_now()
        return record

    target = branch_push_target(spec)
    try:
        grant = consume_approved_request(
            sac_root,
            run_id,
            branch_push_request_id,
            tenant_id=tenant_id,
            action=Action.github_branch_push,
            policy_snapshot_id=policy_snapshot_id,
            target=target,
        )
    except (PermissionError, WorkflowError) as exc:
        record.outcome = "blocked"
        record.output_excerpt = redact_secrets(str(exc))[:256]
        record.ended_at = _utc_now()
        return record

    record.grant_id = grant.grant_id
    client = GitHubBranchClient.from_owner_repo(
        owner=spec.owner,
        repo=spec.repo,
        access_token=access_token,
        api_base_url=spec.api_base_url,
        transport=transport,
    )
    try:
        outcome = client.create_branch_ref(
            branch_name=spec.branch_name,
            commit_sha=spec.commit_sha,
        )
    except ConnectorError as exc:
        record.outcome = "error"
        record.output_excerpt = redact_secrets(str(exc))[:256]
        record.ended_at = _utc_now()
        return record

    audit = EnterpriseAuditChain(project_root_for_sac(sac_root))
    audit.emit(
        AuditEventKind.tool_call_executed,
        run_id=run_id,
        actor_id=actor_id,
        tenant_id=tenant_id,
        payload={
            "tool_name": "github_branch_push",
            "branch_name": outcome.branch_name,
            "ref_sha": outcome.ref_sha,
        },
    )
    record.outcome = "ok"
    record.output_excerpt = f"branch={outcome.branch_name} sha={outcome.ref_sha}"[:256]
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
            "tool_name": "github_branch_push",
            "branch_name": outcome.branch_name,
            "grant_id": grant.grant_id,
        },
    )
    return record


def create_pull_request_governed(
    *,
    sac_root: Path,
    run_id: str,
    node_name: str,
    spec: PRCreateSpec,
    actor_id: str,
    tenant_id: str,
    policy_snapshot_id: str,
    pr_create_request_id: str,
    access_token: SecretStr,
    transport: httpx.BaseTransport | None = None,
) -> ToolCallRecord:
    call_id = f"tool-{uuid.uuid4().hex[:12]}"
    started = _utc_now()
    redacted_body = redact_secrets(spec.body)[:MAX_PR_BODY_CHARS]
    record = ToolCallRecord(
        call_id=call_id,
        run_id=run_id,
        node_name=node_name,
        tool_name="github_pr_create",
        tool_category="write_network",
        inputs_redacted={
            "owner": spec.owner,
            "repo": spec.repo,
            "head_branch": spec.head_branch,
            "base_branch": spec.base_branch,
            "title": spec.title[:128],
        },
        decision=ApprovalDecision(
            decision="GATE",
            reason="governed PR create",
            policy_snapshot_id=policy_snapshot_id,
            inputs=ApprovalDecisionInputs(policy_value="GATE", rbac_value="GATE", tool_spec_value="GATE"),
        ),
        started_at=started,
    )

    target = pr_create_target(spec)
    try:
        grant = consume_approved_request(
            sac_root,
            run_id,
            pr_create_request_id,
            tenant_id=tenant_id,
            action=Action.github_pr_create,
            policy_snapshot_id=policy_snapshot_id,
            target=target,
        )
    except (PermissionError, WorkflowError) as exc:
        record.outcome = "blocked"
        record.output_excerpt = redact_secrets(str(exc))[:256]
        record.ended_at = _utc_now()
        return record

    record.grant_id = grant.grant_id
    client = GitHubBranchClient.from_owner_repo(
        owner=spec.owner,
        repo=spec.repo,
        access_token=access_token,
        api_base_url=spec.api_base_url,
        transport=transport,
    )
    try:
        outcome = client.create_pull_request(
            title=spec.title,
            body=redacted_body,
            head_branch=spec.head_branch,
            base_branch=spec.base_branch,
        )
    except ConnectorError as exc:
        record.outcome = "error"
        record.output_excerpt = redact_secrets(str(exc))[:256]
        record.ended_at = _utc_now()
        return record

    audit = EnterpriseAuditChain(project_root_for_sac(sac_root))
    audit.emit(
        AuditEventKind.tool_call_executed,
        run_id=run_id,
        actor_id=actor_id,
        tenant_id=tenant_id,
        payload={
            "tool_name": "github_pr_create",
            "pr_number": str(outcome.pr_number),
            "head_branch": spec.head_branch,
        },
    )
    record.outcome = "ok"
    record.output_excerpt = f"pr_number={outcome.pr_number}"[:256]
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
            "tool_name": "github_pr_create",
            "pr_number": str(outcome.pr_number),
            "grant_id": grant.grant_id,
        },
    )
    return record


def execute_secure_change(
    *,
    sac_root: Path,
    run_id: str,
    node_name: str,
    branch_spec: BranchPushSpec,
    pr_spec: PRCreateSpec,
    actor_id: str,
    tenant_id: str,
    policy_snapshot_id: str,
    branch_push_request_id: str,
    pr_create_request_id: str,
    access_token: SecretStr,
    transport: httpx.BaseTransport | None = None,
) -> tuple[ToolCallRecord, ToolCallRecord, SecureChangeOutcome]:
    """Push one namespaced branch and open one PR under separate single-use grants."""
    branch_record = push_branch_governed(
        sac_root=sac_root,
        run_id=run_id,
        node_name=node_name,
        spec=branch_spec,
        actor_id=actor_id,
        tenant_id=tenant_id,
        policy_snapshot_id=policy_snapshot_id,
        branch_push_request_id=branch_push_request_id,
        access_token=access_token,
        transport=transport,
    )
    if branch_record.outcome != "ok":
        raise ConnectorError("branch push did not succeed")

    pr_record = create_pull_request_governed(
        sac_root=sac_root,
        run_id=run_id,
        node_name=node_name,
        spec=pr_spec,
        actor_id=actor_id,
        tenant_id=tenant_id,
        policy_snapshot_id=policy_snapshot_id,
        pr_create_request_id=pr_create_request_id,
        access_token=access_token,
        transport=transport,
    )
    if pr_record.outcome != "ok":
        raise ConnectorError("PR create did not succeed")

    branch_outcome = BranchPushOutcome(
        branch_name=branch_spec.branch_name,
        ref_sha=branch_record.output_excerpt.split("sha=", 1)[-1],
    )
    pr_number = int(pr_record.output_excerpt.removeprefix("pr_number="))
    outcome = SecureChangeOutcome(
        branch=branch_outcome,
        pull_request=PRCreateOutcome(pr_number=pr_number),
    )
    return branch_record, pr_record, outcome
