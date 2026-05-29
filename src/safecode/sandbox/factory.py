"""Sandbox adapter factory.

Selects the appropriate sandbox adapter based on the planner's
recommendation, with automatic fallback to noop.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.policy.commands import CommandPolicy
from safecode.sandbox.adapter import (
    DockerSandboxAdapter,
    LinuxBubblewrapAdapter,
    MacOSSeatbeltAdapter,
    NoopSandboxAdapter,
    SandboxAdapter,
    SandboxExecutionRequest,
    SandboxExecutionPlan,
)
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability, SandboxCapabilityDetector
from safecode.sandbox.filesystem import FilesystemBoundary
from safecode.sandbox.planner import SandboxPlanner
from safecode.utils.time import utc_now_iso


class SandboxAdapterFactory:
    """Create the appropriate sandbox adapter for the current environment."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.detector = SandboxCapabilityDetector()
        self.planner = SandboxPlanner(project_root, self.config)
        self.audit_logger = AuditLogger(project_root, self.config)

    def create(self) -> SandboxAdapter:
        """Return the best available adapter for the current system."""
        plan = self.planner.plan()
        return self._adapter_for(plan.recommended_backend, plan.capabilities)

    def create_plan(
        self,
        command: list[str],
        purpose: str = "shell",
        allow_network: bool | None = None,
        readonly_filesystem: bool = True,
        writable_paths: list[Path] | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: int = 30,
    ) -> SandboxExecutionPlan:
        """Build a sandbox execution plan, respecting security policies."""
        command_text = shlex.join(command)
        decision = CommandPolicy(self.config).evaluate(command_text, approved=True)
        if not decision.allowed:
            command_head = command[0] if command else ""
            self._audit(
                "sandbox_plan_blocked",
                "none",
                purpose,
                bool(allow_network),
                command_head,
                decision.reason,
            )
            raise PermissionError(decision.reason)

        network = allow_network if allow_network is not None else self.config.sandbox.network_enabled
        if allow_network and not self.config.sandbox.network_enabled:
            network = False
        safe_writable_paths = self._validate_writable_paths(writable_paths or [])

        request = SandboxExecutionRequest(
            command=command,
            cwd=self.project_root,
            purpose=purpose,
            allow_network=network,
            readonly_filesystem=readonly_filesystem,
            writable_paths=safe_writable_paths,
            env=env or {},
            timeout_seconds=timeout_seconds,
        )

        adapter = self.create()
        plan = adapter.build_plan(request)

        self._audit(
            "sandbox_plan_created",
            plan.backend.value,
            purpose,
            network,
            command[0] if command else "",
            "Sandbox plan created.",
        )
        return plan

    def _validate_writable_paths(self, writable_paths: list[Path]) -> list[Path]:
        """Resolve writable paths and reject project-root escapes."""
        boundary = FilesystemBoundary(self.project_root, self.config)
        return [boundary.validate(path) for path in writable_paths]

    def _adapter_for(
        self, backend: SandboxBackend, capabilities: list[SandboxCapability]
    ) -> SandboxAdapter:
        by_backend = {cap.backend: cap for cap in capabilities}

        if backend == SandboxBackend.LINUX_BUBBLEWRAP:
            cap = by_backend.get(SandboxBackend.LINUX_BUBBLEWRAP)
            if cap and cap.available:
                return LinuxBubblewrapAdapter(cap, project_root=self.project_root, config=self.config)

        if backend == SandboxBackend.MACOS_SEATBELT:
            cap = by_backend.get(SandboxBackend.MACOS_SEATBELT)
            if cap and cap.available:
                return MacOSSeatbeltAdapter(cap, project_root=self.project_root, config=self.config)

        if backend == SandboxBackend.DOCKER:
            cap = by_backend.get(SandboxBackend.DOCKER)
            if cap and cap.available:
                return DockerSandboxAdapter(cap, project_root=self.project_root, config=self.config)

        return NoopSandboxAdapter()

    def _audit(
        self,
        event_type: str,
        backend: str,
        purpose: str,
        network_enabled: bool,
        command_head: str,
        message: str,
    ) -> None:
        self.audit_logger.write(
            AuditEvent(
                type=event_type,
                timestamp=utc_now_iso(),
                status="success" if event_type.endswith("_created") else "blocked",
                message=message,
                metadata={
                    "backend": backend,
                    "purpose": purpose,
                    "dry_run": "true",
                    "network_enabled": str(network_enabled).lower(),
                    "command_head": command_head,
                },
            )
        )
