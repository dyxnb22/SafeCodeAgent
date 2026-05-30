"""Sandbox execution approval model and store for v1.7.6.

User-level persistence of explicit sandbox execution approvals.
Approval files live outside the project root and are never shipped with code.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from safecode import __version__ as SAFECODE_VERSION

SANDBOX_APPROVAL_POLICY_VERSION = f"{SAFECODE_VERSION}-sandbox-approval-v1"
REQUIRED_APPROVAL_FIELDS = {
    "proposal_id",
    "approved_at",
    "expires_at",
    "project_root",
    "project_key",
    "backend",
    "command_hash",
    "preview_hash",
    "approved_by",
    "policy_version",
}


@dataclass(frozen=True)
class SandboxExecutionApproval:
    """User-level, single-use approval for one sandbox execution proposal."""

    proposal_id: str
    approved_at: str
    expires_at: str
    project_root: str
    project_key: str
    backend: str
    command_hash: str
    preview_hash: str | None
    approved_by: str
    policy_version: str
    consumed: bool = False


class SandboxExecutionApprovalStore:
    """File-backed sandbox execution approval registry.

    Approvals are stored OUTSIDE the project root so that a project
    cannot ship pre-approved execution files.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._approval_root = self._resolve_approval_root()

    def approve(
        self,
        proposal_id: str,
        backend: str,
        command_hash: str,
        preview_hash: str | None,
        ttl_minutes: int = 30,
    ) -> SandboxExecutionApproval:
        now = datetime.now(timezone.utc)
        approval = SandboxExecutionApproval(
            proposal_id=proposal_id,
            approved_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=ttl_minutes)).isoformat(),
            project_root=str(self.project_root),
            project_key=self._project_key(),
            backend=backend,
            command_hash=command_hash,
            preview_hash=preview_hash,
            approved_by=self._current_user(),
            policy_version=SANDBOX_APPROVAL_POLICY_VERSION,
        )
        path = self._approval_path_for(proposal_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "proposal_id": approval.proposal_id,
            "approved_at": approval.approved_at,
            "expires_at": approval.expires_at,
            "project_root": approval.project_root,
            "project_key": approval.project_key,
            "backend": approval.backend,
            "command_hash": approval.command_hash,
            "preview_hash": approval.preview_hash,
            "approved_by": approval.approved_by,
            "policy_version": approval.policy_version,
            "consumed": False,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return approval

    def is_approved(
        self,
        proposal_id: str,
        backend: str,
        command_hash: str,
        preview_hash: str | None,
    ) -> bool:
        approval = self._load(proposal_id)
        if approval is None:
            return False
        if approval.proposal_id != proposal_id:
            return False
        if approval.backend != backend:
            return False
        if approval.command_hash != command_hash:
            return False
        if approval.preview_hash != preview_hash:
            return False
        if approval.project_key != self._project_key():
            return False
        if approval.policy_version != SANDBOX_APPROVAL_POLICY_VERSION:
            return False
        try:
            expires = datetime.fromisoformat(approval.expires_at)
            if datetime.now(timezone.utc) >= expires:
                return False
        except (ValueError, TypeError):
            return False
        if approval.consumed:
            return False
        return True

    def consume(self, proposal_id: str) -> bool:
        """Mark an approval as consumed (single-use). Returns False if missing or
        already consumed."""
        approval = self._load(proposal_id)
        if approval is None or approval.consumed:
            return False
        path = self._approval_path_for(proposal_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        data["consumed"] = True
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return True

    def revoke(self, proposal_id: str) -> bool:
        path = self._approval_path_for(proposal_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def load_approval(self, proposal_id: str) -> SandboxExecutionApproval | None:
        return self._load(proposal_id)

    def approval_path_for(self, proposal_id: str) -> Path:
        return self._approval_path_for(proposal_id)

    # -- internal --

    def _load(self, proposal_id: str) -> SandboxExecutionApproval | None:
        path = self._approval_path_for(proposal_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not REQUIRED_APPROVAL_FIELDS.issubset(data.keys()):
            return None
        try:
            approval_data = {k: data[k] for k in REQUIRED_APPROVAL_FIELDS}
            approval_data["consumed"] = data.get("consumed", False)
            return SandboxExecutionApproval(**approval_data)
        except (TypeError, ValueError):
            return None

    def _approval_path_for(self, proposal_id: str) -> Path:
        safe_id = hashlib.sha256(proposal_id.encode("utf-8")).hexdigest()
        return self._approval_root / f"{safe_id}.json"

    def _project_key(self) -> str:
        return hashlib.sha256(self.project_root.as_posix().encode("utf-8")).hexdigest()

    @staticmethod
    def _current_user() -> str:
        return os.environ.get("USER", os.environ.get("USERNAME", "unknown"))

    def _resolve_approval_root(self) -> Path:
        env_dir = os.environ.get("SAFECODE_SANDBOX_APPROVAL_DIR")
        if env_dir:
            path = Path(env_dir).expanduser().resolve()
            if self._is_inside_project(path):
                raise PermissionError(
                    "SAFECODE_SANDBOX_APPROVAL_DIR must be outside the project root. "
                    "A project cannot ship its own sandbox approvals."
                )
            return path
        return Path.home() / ".safecode" / "sandbox_approvals"

    def _is_inside_project(self, path: Path) -> bool:
        try:
            path.relative_to(self.project_root)
            return True
        except ValueError:
            return False
