"""Approval request persistence."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from safecode.context.redactor import redact_secrets
from safecode.enterprise.workflow.exceptions import (
    ApprovalRequestExistsError,
    ApprovalRequestNotFoundError,
    ApprovalRequestTamperedError,
    InvalidRunIdError,
    RequestAlreadyConsumedError,
)
from safecode.enterprise.workflow.ids import validate_run_id
from safecode.enterprise.workflow.types import RiskTier


class Action(str, Enum):
    file_write = "file_write"
    command_execute = "command_execute"
    scanner_run = "scanner_run"
    github_read = "github_read"
    github_write_comment = "github_write_comment"
    github_branch_push = "github_branch_push"
    github_pr_create = "github_pr_create"
    issue_comment = "issue_comment"
    mcp_read = "mcp_read"
    mcp_write = "mcp_write"
    retrieval_source_access = "retrieval_source_access"
    memory_fact_inject = "memory_fact_inject"
    policy_config_change = "policy_config_change"
    production_access = "production_access"


ApprovalStatus = Literal["pending", "approved", "rejected", "evidence_requested", "revoked"]


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    run_id: str
    action: Action
    risk_tier: RiskTier
    requested_by_node: str
    requesting_actor: str
    target: dict[str, str] = Field(default_factory=dict)
    preview: str = ""
    policy_snapshot_id: str
    status: ApprovalStatus = "pending"
    created_at: str
    decision_at: str | None = None
    decision_actor: str | None = None
    decision_note: str | None = None
    request_hash: str = ""


class ApprovalDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    run_id: str
    decision: Literal["approved", "rejected"]
    decision_actor: str
    decision_note: str = ""
    decided_at: str
    request_hash: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def request_hash(request: ApprovalRequest) -> str:
    payload = request.model_copy(update={"request_hash": ""}).model_dump_json()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def approvals_dir(sac_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    root = (sac_root / "enterprise" / "runs").resolve()
    directory = (root / run_id / "approvals").resolve()
    if root not in directory.parents:
        raise InvalidRunIdError(f"approval path escapes runs root for {run_id!r}")
    return directory


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(tmp, path)


_REQUEST_ID_RE = re.compile(r"^approval-[a-zA-Z0-9_-]{8,64}$")


def validate_request_id(request_id: str) -> str:
    if not isinstance(request_id, str) or not _REQUEST_ID_RE.match(request_id):
        raise InvalidRunIdError(f"invalid request_id: {request_id!r}")
    if ".." in request_id or "/" in request_id or "\\" in request_id:
        raise InvalidRunIdError(f"invalid request_id path characters: {request_id!r}")
    return request_id


def save_request(sac_root: Path, request: ApprovalRequest) -> ApprovalRequest:
    validate_request_id(request.request_id)
    directory = approvals_dir(sac_root, request.run_id)
    path = directory / f"{request.request_id}.json"
    if path.exists():
        raise ApprovalRequestExistsError(f"approval request exists: {request.request_id}")
    redacted = request.model_copy(update={"preview": redact_secrets(request.preview)[:4096]})
    redacted = redacted.model_copy(update={"request_hash": request_hash(redacted)})
    _atomic_write(path, json.loads(redacted.model_dump_json()))
    return redacted


def load_request(sac_root: Path, run_id: str, request_id: str) -> ApprovalRequest:
    validate_request_id(request_id)
    path = approvals_dir(sac_root, run_id) / f"{request_id}.json"
    if not path.is_file():
        raise ApprovalRequestNotFoundError(f"approval request not found: {request_id}")
    request = ApprovalRequest.model_validate_json(path.read_text(encoding="utf-8"))
    if request.request_hash != request_hash(request):
        raise ApprovalRequestTamperedError(f"approval request tampered: {request_id}")
    return request


def list_requests(sac_root: Path, run_id: str) -> list[ApprovalRequest]:
    directory = approvals_dir(sac_root, run_id)
    if not directory.is_dir():
        return []
    items: list[ApprovalRequest] = []
    for path in sorted(directory.glob("*.json")):
        items.append(ApprovalRequest.model_validate_json(path.read_text(encoding="utf-8")))
    return items


def decide_request(
    sac_root: Path,
    run_id: str,
    request_id: str,
    *,
    decision: Literal["approved", "rejected"],
    decision_actor: str,
    decision_note: str = "",
) -> ApprovalRequest:
    if decision_actor.startswith("model:"):
        raise PermissionError("model actors cannot approve their own requests")
    request = load_request(sac_root, run_id, request_id)
    if request.status != "pending":
        raise RequestAlreadyConsumedError(f"approval request already decided: {request_id}")
    updated = request.model_copy(
        update={
            "status": decision,
            "decision_at": _utc_now(),
            "decision_actor": decision_actor,
            "decision_note": redact_secrets(decision_note),
        }
    )
    updated = updated.model_copy(update={"request_hash": request_hash(updated)})
    _atomic_write(
        approvals_dir(sac_root, run_id) / f"{request_id}.json",
        json.loads(updated.model_dump_json()),
    )
    return updated
