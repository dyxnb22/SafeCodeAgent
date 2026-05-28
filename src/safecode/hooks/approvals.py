"""Persist explicit hook approvals."""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from safecode import __version__ as SAFECODE_VERSION
from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.utils.time import utc_now_iso


@dataclass(frozen=True)
class HookApproval:
    """One stored hook approval."""

    hook_name: str
    command: str
    command_hash: str
    approved_at: str
    expires_at: str
    user: str
    config_hash: str
    policy_version: str


APPROVAL_POLICY_VERSION = f"{SAFECODE_VERSION}-hook-approval-v1"
REQUIRED_APPROVAL_FIELDS = {
    "hook_name",
    "command",
    "command_hash",
    "approved_at",
    "expires_at",
    "user",
    "config_hash",
    "policy_version",
}


class HookApprovalStore:
    """File-backed hook approval registry."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.path = self._approval_dir() / f"{self._project_key()}.jsonl"
        self.audit_logger = AuditLogger(project_root, self.config)

    def approve(self, hook_name: str, command: str, ttl_hours: int = 24) -> HookApproval:
        """Persist approval for one exact hook command."""
        approved_at = utc_now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat().replace("+00:00", "Z")
        approval = HookApproval(
            hook_name=hook_name,
            command=command,
            command_hash=self.command_hash(hook_name, command),
            approved_at=approved_at,
            expires_at=expires_at,
            user=self._current_user(),
            config_hash=self.config_hash(),
            policy_version=self._policy_version(),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(approval.__dict__, ensure_ascii=False, sort_keys=True) + "\n")
        self.path.chmod(0o600)
        self.audit_logger.write(
            AuditEvent(
                type="hook_approved",
                timestamp=approval.approved_at,
                status="success",
                command=command,
                message="hook command approved explicitly",
                metadata={
                    "hook": hook_name,
                    "command_hash": approval.command_hash,
                    "expires_at": approval.expires_at,
                    "user": approval.user,
                    "config_hash": approval.config_hash,
                    "policy_version": approval.policy_version,
                },
            )
        )
        return approval

    def is_approved(self, hook_name: str, command: str) -> bool:
        """Return true when an exact approval exists."""
        expected_hash = self.command_hash(hook_name, command)
        expected_config = self.config_hash()
        current_user = self._current_user()
        return any(
            approval.command_hash == expected_hash
            and approval.config_hash == expected_config
            and approval.policy_version == self._policy_version()
            and approval.user == current_user
            and not self._is_expired(approval)
            for approval in self.list()
        )

    def list(self) -> list[HookApproval]:
        """Read stored approvals."""
        if not self.path.exists():
            return []
        approvals: list[HookApproval] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                if not REQUIRED_APPROVAL_FIELDS.issubset(payload.keys()):
                    continue
                if not all(isinstance(payload[field], str) for field in REQUIRED_APPROVAL_FIELDS):
                    continue
                try:
                    approvals.append(HookApproval(**payload))
                except TypeError:
                    continue
        return approvals

    def command_hash(self, hook_name: str, command: str) -> str:
        """Hash hook identity and command for exact approval lookup."""
        payload = json.dumps({"hook": hook_name, "command": command}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def config_hash(self) -> str:
        """Hash the hook-relevant effective config."""
        payload = {
            "allow_medium_after_apply": self.config.hooks.allow_medium_after_apply,
            "after_apply": self.config.hooks.after_apply,
            "allowed_commands": self.config.shell.allowed_commands,
            "require_confirm_for_medium": self.config.shell.require_confirm_for_medium,
            "block_high_risk": self.config.shell.block_high_risk,
            "policy": self.config.policy,
            "policy_version": self._policy_version(),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _approval_dir(self) -> Path:
        """Return trusted user-level approval directory."""
        env_path = os.getenv("SAFECODE_APPROVAL_DIR")
        if env_path:
            return Path(env_path).expanduser()
        return Path.home() / ".safecode" / "approvals" / "hooks"

    def _project_key(self) -> str:
        """Create a stable user-level approval filename for this project."""
        return hashlib.sha256(str(self.project_root.resolve()).encode("utf-8")).hexdigest()

    def _current_user(self) -> str:
        """Return a simple local user identity for approval binding."""
        return os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    def _is_expired(self, approval: HookApproval) -> bool:
        """Return true when an approval has expired."""
        try:
            expires_at = approval.expires_at.replace("Z", "+00:00")
            return datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc)
        except (ValueError, TypeError):
            return True

    def _policy_version(self) -> str:
        """Return the approval policy version for binding."""
        return APPROVAL_POLICY_VERSION
