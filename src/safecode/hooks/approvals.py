"""Persist explicit hook approvals."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

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


class HookApprovalStore:
    """File-backed hook approval registry."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.path = project_root / self.config.sac_dir / "approvals" / "hooks.jsonl"
        self.audit_logger = AuditLogger(project_root, self.config)

    def approve(self, hook_name: str, command: str) -> HookApproval:
        """Persist approval for one exact hook command."""
        approval = HookApproval(
            hook_name=hook_name,
            command=command,
            command_hash=self.command_hash(hook_name, command),
            approved_at=utc_now_iso(),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(approval.__dict__, ensure_ascii=False, sort_keys=True) + "\n")
        self.audit_logger.write(
            AuditEvent(
                type="hook_approved",
                timestamp=approval.approved_at,
                status="success",
                command=command,
                message="hook command approved explicitly",
                metadata={"hook": hook_name, "command_hash": approval.command_hash},
            )
        )
        return approval

    def is_approved(self, hook_name: str, command: str) -> bool:
        """Return true when an exact approval exists."""
        expected_hash = self.command_hash(hook_name, command)
        return any(approval.command_hash == expected_hash for approval in self.list())

    def list(self) -> list[HookApproval]:
        """Read stored approvals."""
        if not self.path.exists():
            return []
        approvals: list[HookApproval] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                approvals.append(HookApproval(**json.loads(line)))
        return approvals

    def command_hash(self, hook_name: str, command: str) -> str:
        """Hash hook identity and command for exact approval lookup."""
        payload = json.dumps({"hook": hook_name, "command": command}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
