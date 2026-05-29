"""Sandbox execution preflight check for v1.7.8.

Unified decision layer that checks all preconditions for sandbox execution
without actually executing anything. Returns a structured check result
showing which conditions pass and which fail.
"""

from __future__ import annotations

import hashlib
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.policy.commands import CommandPolicy
from safecode.sandbox.approvals import SandboxExecutionApprovalStore
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapabilityDetector
from safecode.sandbox.execution import SandboxExecutionProposal, SandboxExecutionProposalStore
from safecode.sandbox.filesystem import FilesystemBoundary
from safecode.sandbox.adapter import (
    DockerSandboxAdapter,
    LinuxBubblewrapAdapter,
    MacOSSeatbeltAdapter,
    NoopSandboxAdapter,
)
from safecode.utils.time import utc_now_iso


@dataclass(frozen=True)
class SandboxPreflightCheckResult:
    """Result of running all sandbox execution precondition checks."""

    allowed: bool
    proposal_id: str | None
    backend: str
    command_head: str
    approval_valid: bool
    command_policy_ok: bool
    network_policy_ok: bool
    backend_available: bool
    backend_supports_execution: bool
    proposal_integrity_ok: bool
    preview_hash_ok: bool
    filesystem_boundary_ok: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SandboxExecutionPreflight:
    """Run all preflight checks for a pending sandbox execution proposal.

    Gathers proposal, approval, command policy, network policy, backend
    capability, preview hash, and filesystem boundary into a single
    decision object. Never executes any external command.
    """

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.proposal_store = SandboxExecutionProposalStore(project_root, self.config)
        self.audit_logger = AuditLogger(project_root, self.config)

    def run(self) -> SandboxPreflightCheckResult:
        """Run all checks and return a structured result."""
        reasons: list[str] = []
        proposal = self._load_proposal()
        if proposal is None:
            reason = (
                "Malformed pending sandbox execution proposal."
                if self.proposal_store.path.exists()
                else "No pending sandbox execution proposal."
            )
            result = SandboxPreflightCheckResult(
                allowed=False,
                proposal_id=None,
                backend="none",
                command_head="",
                approval_valid=False,
                command_policy_ok=False,
                network_policy_ok=False,
                backend_available=False,
                backend_supports_execution=False,
                proposal_integrity_ok=False,
                preview_hash_ok=False,
                filesystem_boundary_ok=False,
                reasons=[reason],
            )
            self._audit(result)
            return result

        proposal_integrity_ok = self._check_proposal_integrity(proposal)
        approval_valid = self._check_approval(proposal)
        command_policy_ok = self._check_command_policy(proposal)
        network_policy_ok = self._check_network_policy(proposal)
        backend_available, backend_supports_execution = self._check_backend(proposal)
        preview_hash_ok = self._check_preview_hash(proposal)
        filesystem_boundary_ok = self._check_filesystem_boundary(proposal)

        if not proposal_integrity_ok:
            reasons.append("Proposal command hash does not match the stored command.")
        if not approval_valid:
            reasons.append("Approval is missing, expired, or mismatched.")
        if not command_policy_ok:
            reasons.append("Command is not allowed by CommandPolicy.")
        if not network_policy_ok:
            reasons.append("Network policy conflict: proposal requires network but config disables it.")
        if not backend_available:
            reasons.append(f"Backend '{proposal.backend}' is not available on this system.")
        if not backend_supports_execution:
            reasons.append(f"Backend '{proposal.backend}' does not support execution (all adapters in v1.7.x return False).")
        if not filesystem_boundary_ok:
            reasons.append("One or more writable paths escape project root.")

        all_checks = [
            proposal_integrity_ok,
            approval_valid,
            command_policy_ok,
            network_policy_ok,
            backend_available,
            backend_supports_execution,
            preview_hash_ok,
            filesystem_boundary_ok,
        ]
        allowed = all(all_checks)

        result = SandboxPreflightCheckResult(
            allowed=allowed,
            proposal_id=proposal.proposal_id,
            backend=proposal.backend,
            command_head=proposal.command[0] if proposal.command else "",
            approval_valid=approval_valid,
            command_policy_ok=command_policy_ok,
            network_policy_ok=network_policy_ok,
            backend_available=backend_available,
            backend_supports_execution=backend_supports_execution,
            proposal_integrity_ok=proposal_integrity_ok,
            preview_hash_ok=preview_hash_ok,
            filesystem_boundary_ok=filesystem_boundary_ok,
            reasons=reasons,
        )
        self._audit(result)
        return result

    def _load_proposal(self) -> SandboxExecutionProposal | None:
        return self.proposal_store.load_pending()

    def _check_approval(self, proposal: SandboxExecutionProposal) -> bool:
        store = SandboxExecutionApprovalStore(self.project_root)
        return store.is_approved(
            proposal_id=proposal.proposal_id,
            backend=proposal.backend,
            command_hash=proposal.command_hash,
            preview_hash=proposal.preview_hash,
        )

    def _check_command_policy(self, proposal: SandboxExecutionProposal) -> bool:
        cmd_text = shlex.join(proposal.command)
        decision = CommandPolicy(self.config).evaluate(cmd_text, approved=True)
        return decision.allowed

    def _check_network_policy(self, proposal: SandboxExecutionProposal) -> bool:
        if proposal.network_enabled and not self.config.sandbox.network_enabled:
            return False
        return True

    def _check_backend(self, proposal: SandboxExecutionProposal) -> tuple[bool, bool]:
        try:
            target = SandboxBackend(proposal.backend)
        except ValueError:
            return False, False
        detector = SandboxCapabilityDetector()
        caps = detector.detect_all()
        by_backend = {cap.backend: cap for cap in caps}
        cap = by_backend.get(target)
        available = cap is not None and cap.available
        if not available or cap is None:
            return available, False
        if target == SandboxBackend.MACOS_SEATBELT:
            adapter = MacOSSeatbeltAdapter(cap, self.project_root, self.config)
        elif target == SandboxBackend.LINUX_BUBBLEWRAP:
            adapter = LinuxBubblewrapAdapter(cap, self.project_root, self.config)
        elif target == SandboxBackend.DOCKER:
            adapter = DockerSandboxAdapter(cap, self.project_root, self.config)
        else:
            adapter = NoopSandboxAdapter()
        supports = adapter.supports_execution()
        return available, supports

    def _check_proposal_integrity(self, proposal: SandboxExecutionProposal) -> bool:
        return proposal.command_hash == _hash_values(proposal.command)

    def _check_preview_hash(self, proposal: SandboxExecutionProposal) -> bool:
        if proposal.preview_kind in {"profile", "args", "container"}:
            return bool(proposal.preview_hash)
        return proposal.preview_kind == "none" and proposal.preview_hash is None

    def _check_filesystem_boundary(self, proposal: SandboxExecutionProposal) -> bool:
        boundary = FilesystemBoundary(self.project_root, self.config)
        for path_str in proposal.writable_paths:
            try:
                boundary.validate(Path(path_str))
            except PermissionError:
                return False
        return True

    def _audit(self, result: SandboxPreflightCheckResult) -> None:
        status = "success" if result.allowed else "blocked"
        self.audit_logger.write(
            AuditEvent(
                type="sandbox_preflight_checked",
                timestamp=utc_now_iso(),
                status=status,
                message="Preflight check completed." if result.allowed else "Preflight check blocked.",
                metadata={
                    "proposal_id": result.proposal_id or "none",
                    "backend": result.backend,
                    "command_head": result.command_head,
                    "allowed": str(result.allowed).lower(),
                    "approval_valid": str(result.approval_valid).lower(),
                    "proposal_integrity_ok": str(result.proposal_integrity_ok).lower(),
                    "backend_supports_execution": str(result.backend_supports_execution).lower(),
                },
            )
        )


def _hash_values(values: list[str]) -> str:
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
