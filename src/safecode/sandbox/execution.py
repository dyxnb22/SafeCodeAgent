"""Sandbox execution gate for v1.7.5+.  Real execution added in v1.8.0.

v1.7.5: proposal models, persistence, dry-run rejection only.
v1.8.0: Noop adapter executes commands through SafeCode logical boundaries
when all preflight checks pass. macOS/Linux/Docker backends remain dry-run.
"""

from __future__ import annotations

import hashlib
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import SandboxExecutionPlan
from safecode.sandbox.approvals import SandboxExecutionApproval, SandboxExecutionApprovalStore
from safecode.shell.runner import ShellRunner
from safecode.utils.time import utc_now_iso


@dataclass(frozen=True)
class SandboxExecutionProposal:
    """A pending sandbox execution proposal."""

    proposal_id: str
    created_at: str
    backend: str
    command: list[str]
    command_hash: str
    purpose: str
    cwd: str
    network_enabled: bool
    readonly_filesystem: bool
    writable_paths: list[str]
    env_keys: list[str]
    preview_kind: str
    preview_hash: str | None
    status: str = "pending"
    risk_reason: str | None = None


@dataclass(frozen=True)
class SandboxExecutionResult:
    """Result of a sandbox execution attempt."""

    proposal_id: str
    executed: bool
    exit_code: int | None
    stdout: str
    stderr: str
    backend: str
    dry_run: bool
    message: str


class SandboxExecutionProposalStore:
    """Persist a single pending sandbox execution proposal."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.path = project_root / self.config.sac_dir / "pending_sandbox_execution.json"

    def create(self, proposal: SandboxExecutionProposal) -> SandboxExecutionProposal:
        if self.exists():
            if self.load_pending() is None:
                raise FileExistsError(
                    "A corrupt pending sandbox execution proposal exists. "
                    "Discard it first with 'sac sandbox discard'."
                )
            raise FileExistsError(
                "A pending sandbox execution proposal already exists. "
                "Discard it first with 'sac sandbox discard'."
            )
        self._write(proposal)
        return proposal

    def load_pending(self) -> SandboxExecutionProposal | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return SandboxExecutionProposal(**data)
        except (json.JSONDecodeError, TypeError):
            return None

    def discard_pending(self) -> bool:
        if self.path.exists():
            self.path.unlink()
            return True
        return False

    def exists(self) -> bool:
        return self.path.exists()

    def _write(self, proposal: SandboxExecutionProposal) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "proposal_id": proposal.proposal_id,
            "created_at": proposal.created_at,
            "backend": proposal.backend,
            "command": proposal.command,
            "command_hash": proposal.command_hash,
            "purpose": proposal.purpose,
            "cwd": proposal.cwd,
            "network_enabled": proposal.network_enabled,
            "readonly_filesystem": proposal.readonly_filesystem,
            "writable_paths": proposal.writable_paths,
            "env_keys": proposal.env_keys,
            "preview_kind": proposal.preview_kind,
            "preview_hash": proposal.preview_hash,
            "status": proposal.status,
            "risk_reason": proposal.risk_reason,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class SandboxExecutionGate:
    """Gate that controls sandbox execution proposal lifecycle.

    v1.7.5: proposal creation, persistence, and rejection only.
    Real execution is NOT enabled.
    """

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.store = SandboxExecutionProposalStore(project_root, self.config)
        self.audit_logger = AuditLogger(project_root, self.config)

    def propose(self, plan: SandboxExecutionPlan, purpose: str) -> SandboxExecutionProposal:
        """Create a pending sandbox execution proposal from a plan."""
        preview_kind = self._preview_kind(plan)
        preview_hash = self._hash_preview(plan, preview_kind)
        proposal = SandboxExecutionProposal(
            proposal_id=str(uuid4()),
            created_at=utc_now_iso(),
            backend=plan.backend.value,
            command=list(plan.command),
            command_hash=self._hash_command(plan.command),
            purpose=purpose,
            cwd=plan.cwd,
            network_enabled=plan.network_enabled,
            readonly_filesystem=plan.readonly_filesystem,
            writable_paths=list(plan.writable_paths),
            env_keys=sorted(plan.env_keys),
            preview_kind=preview_kind,
            preview_hash=preview_hash,
            status="pending",
        )
        self.store.create(proposal)
        self._audit(
            "sandbox_execution_proposed",
            proposal.proposal_id,
            proposal.backend,
            proposal.purpose,
            proposal.command[0] if proposal.command else "",
            proposal.command_hash,
        )
        return proposal

    def discard(self) -> SandboxExecutionProposal | None:
        """Discard the pending proposal. Returns None if none existed."""
        proposal = self.store.load_pending()
        removed = self.store.discard_pending()
        if proposal and removed:
            self._audit(
                "sandbox_execution_discarded",
                proposal.proposal_id,
                proposal.backend,
                proposal.purpose,
                proposal.command[0] if proposal.command else "",
                proposal.command_hash,
            )
        return proposal

    def block(self, reason: str) -> SandboxExecutionResult:
        proposal = self.store.load_pending()
        proposal_id = proposal.proposal_id if proposal else "unknown"
        backend = proposal.backend if proposal else "none"
        self._audit(
            "sandbox_execution_blocked",
            proposal_id,
            backend,
            "",
            "",
            "",
            reason,
        )
        return SandboxExecutionResult(
            proposal_id=proposal_id,
            executed=False,
            exit_code=None,
            stdout="",
            stderr=reason,
            backend=backend,
            dry_run=True,
            message=reason,
        )

    def approve(self, ttl_minutes: int = 30) -> SandboxExecutionApproval | None:
        """Approve the pending proposal. Returns None if no proposal."""
        proposal = self.store.load_pending()
        if proposal is None:
            return None
        approval_store = SandboxExecutionApprovalStore(self.project_root)
        approval = approval_store.approve(
            proposal_id=proposal.proposal_id,
            backend=proposal.backend,
            command_hash=proposal.command_hash,
            preview_hash=proposal.preview_hash,
            ttl_minutes=ttl_minutes,
        )
        self._audit(
            "sandbox_execution_approved",
            proposal.proposal_id,
            proposal.backend,
            proposal.purpose,
            proposal.command[0] if proposal.command else "",
            proposal.command_hash,
            f"Approved by {approval.approved_by}. Expires: {approval.expires_at}.",
        )
        return approval

    def revoke(self) -> SandboxExecutionApproval | None:
        """Revoke approval for pending proposal. Returns None if no proposal."""
        proposal = self.store.load_pending()
        if proposal is None:
            return None
        approval_store = SandboxExecutionApprovalStore(self.project_root)
        approval = approval_store.load_approval(proposal.proposal_id)
        removed = approval_store.revoke(proposal.proposal_id)
        if removed:
            self._audit(
                "sandbox_execution_approval_revoked",
                proposal.proposal_id,
                proposal.backend,
                proposal.purpose,
                proposal.command[0] if proposal.command else "",
                proposal.command_hash,
                "Approval revoked.",
            )
        return approval

    def load_approval(self) -> SandboxExecutionApproval | None:
        """Load approval for pending proposal."""
        proposal = self.store.load_pending()
        if proposal is None:
            return None
        return SandboxExecutionApprovalStore(self.project_root).load_approval(proposal.proposal_id)

    def execute_pending(self) -> SandboxExecutionResult:
        """Execute the pending proposal when all preflight checks pass.

        v1.8.0: Only the Noop adapter supports execution.
        v1.8.1: Approval is single-use — consumed after first successful
        execution so it cannot be reused within its TTL.
        v1.8.2: Approval is atomically claimed BEFORE ShellRunner.run()
        to close the TOCTOU race between preflight and execution.
        """
        proposal = self.store.load_pending()
        if proposal is None:
            msg = "No pending sandbox execution proposal."
            self._audit(
                "sandbox_execution_blocked",
                "unknown",
                "none",
                "",
                "",
                "",
                msg,
            )
            return SandboxExecutionResult(
                proposal_id="unknown",
                executed=False,
                exit_code=None,
                stdout="",
                stderr=msg,
                backend="none",
                dry_run=True,
                message=msg,
            )

        from safecode.sandbox.preflight import SandboxExecutionPreflight  # lazy to avoid circular import

        preflight = SandboxExecutionPreflight(self.project_root, self.config)
        check = preflight.run()

        if not check.allowed:
            reasons = "; ".join(check.reasons) if check.reasons else "Preflight check failed."
            self._audit(
                "sandbox_execution_blocked",
                proposal.proposal_id,
                proposal.backend,
                proposal.purpose,
                proposal.command[0] if proposal.command else "",
                proposal.command_hash,
                reasons,
            )
            return SandboxExecutionResult(
                proposal_id=proposal.proposal_id,
                executed=False,
                exit_code=None,
                stdout="",
                stderr=reasons,
                backend=proposal.backend,
                dry_run=True,
                message=reasons,
            )

        # v1.8.2: atomically claim approval BEFORE execution to close
        # the TOCTOU window between preflight and ShellRunner.run().
        approval_store = SandboxExecutionApprovalStore(self.project_root)
        claimed = approval_store.claim_for_execution(
            proposal_id=proposal.proposal_id,
            backend=proposal.backend,
            command_hash=proposal.command_hash,
            preview_hash=proposal.preview_hash,
        )
        if not claimed:
            reason = "Approval claim failed: already consumed, expired, or mismatched."
            self._audit(
                "sandbox_execution_blocked",
                proposal.proposal_id,
                proposal.backend,
                proposal.purpose,
                proposal.command[0] if proposal.command else "",
                proposal.command_hash,
                reason,
            )
            return SandboxExecutionResult(
                proposal_id=proposal.proposal_id,
                executed=False,
                exit_code=None,
                stdout="",
                stderr=reason,
                backend=proposal.backend,
                dry_run=True,
                message=reason,
            )

        self._audit(
            "sandbox_execution_approval_claimed",
            proposal.proposal_id,
            proposal.backend,
            proposal.purpose,
            proposal.command[0] if proposal.command else "",
            proposal.command_hash,
            "Approval claimed for execution (atomic).",
        )

        cmd_text = shlex.join(proposal.command)
        runner = ShellRunner(self.project_root, self.config)
        result = runner.run(cmd_text, approved=True)

        self._audit(
            "sandbox_execution_completed",
            proposal.proposal_id,
            proposal.backend,
            proposal.purpose,
            proposal.command[0] if proposal.command else "",
            proposal.command_hash,
            f"exit_code={result.exit_code} duration_ms={result.duration_ms}",
        )
        return SandboxExecutionResult(
            proposal_id=proposal.proposal_id,
            executed=result.executed,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            backend=proposal.backend,
            dry_run=False,
            message=f"Command executed via {proposal.backend} backend. Exit code: {result.exit_code}.",
        )

    @property
    def pending_path(self) -> Path:
        return self.store.path

    def load_pending(self) -> SandboxExecutionProposal | None:
        return self.store.load_pending()

    @staticmethod
    def _preview_kind(plan: SandboxExecutionPlan) -> str:
        if plan.profile_preview:
            return "profile"
        if plan.args_preview:
            return "args"
        if plan.container_preview:
            return "container"
        return "none"

    @staticmethod
    def _hash_preview(plan: SandboxExecutionPlan, kind: str) -> str | None:
        if kind == "profile" and plan.profile_preview:
            return hashlib.sha256(plan.profile_preview.encode("utf-8")).hexdigest()
        if kind == "args" and plan.args_preview:
            return hashlib.sha256(_stable_json(plan.args_preview).encode("utf-8")).hexdigest()
        if kind == "container" and plan.container_preview:
            return hashlib.sha256(_stable_json(plan.container_preview).encode("utf-8")).hexdigest()
        return None

    @staticmethod
    def _hash_command(command: list[str]) -> str:
        return hashlib.sha256(_stable_json(command).encode("utf-8")).hexdigest()

    def _audit(
        self,
        event_type: str,
        proposal_id: str,
        backend: str,
        purpose: str,
        command_head: str,
        command_hash: str,
        extra: str = "",
    ) -> None:
        success_events = {
            "sandbox_execution_proposed",
            "sandbox_execution_discarded",
            "sandbox_execution_approved",
            "sandbox_execution_approval_revoked",
            "sandbox_execution_completed",
            "sandbox_execution_approval_consumed",
            "sandbox_execution_approval_claimed",
        }
        self.audit_logger.write(
            AuditEvent(
                type=event_type,
                timestamp=utc_now_iso(),
                status="success" if event_type in success_events else "blocked",
                message=extra or f"Sandbox execution {event_type.replace('sandbox_execution_', '')}.",
                metadata={
                    "proposal_id": proposal_id,
                    "backend": backend,
                    "purpose": purpose,
                    "dry_run": "false" if event_type == "sandbox_execution_completed" else "true",
                    "command_head": command_head,
                    "command_hash": command_hash[:16],
                },
            )
        )


def _stable_json(values: list[str]) -> str:
    """Return a stable string for hashing argv-like lists without ambiguity."""
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))
