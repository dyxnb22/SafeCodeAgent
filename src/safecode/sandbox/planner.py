"""Sandbox planner: recommend a backend and explain limitations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.sandbox.capabilities import (
    SandboxBackend,
    SandboxCapability,
    SandboxCapabilityDetector,
)
from safecode.utils.time import utc_now_iso


@dataclass(frozen=True)
class SandboxPlan:
    """Recommended sandbox plan with supporting information."""

    platform: str
    recommended_backend: SandboxBackend
    capabilities: list[SandboxCapability]
    active_logical_boundaries: list[str]
    notes: list[str] = field(default_factory=list)


class SandboxPlanner:
    """Detect sandbox capabilities and recommend the best available backend."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)
        self.detector = SandboxCapabilityDetector()
        self.audit_logger = AuditLogger(project_root, self.config)

    def plan(self) -> SandboxPlan:
        """Produce a sandbox plan for the current system."""
        import platform as _platform

        capabilities = self.detector.detect_all()
        backend = self._recommend(capabilities)
        boundaries = self._active_boundaries()
        plan = SandboxPlan(
            platform=_platform.system(),
            recommended_backend=backend,
            capabilities=capabilities,
            active_logical_boundaries=boundaries,
            notes=[
                "OS sandbox is NOT automatically enabled in v1.6.4.",
                "All shell, MCP, and hook execution still goes through "
                "CommandPolicy, NetworkPolicy, and FilesystemBoundary.",
                "This is a research and planning layer for future v1.7+ "
                "OS-level containment.",
            ],
        )
        self._audit(plan)
        return plan

    def _recommend(self, capabilities: list[SandboxCapability]) -> SandboxBackend:
        by_backend = {cap.backend: cap for cap in capabilities}

        bubblewrap = by_backend.get(SandboxBackend.LINUX_BUBBLEWRAP)
        if bubblewrap and bubblewrap.available:
            return SandboxBackend.LINUX_BUBBLEWRAP

        seatbelt = by_backend.get(SandboxBackend.MACOS_SEATBELT)
        if seatbelt and seatbelt.available:
            return SandboxBackend.MACOS_SEATBELT

        docker = by_backend.get(SandboxBackend.DOCKER)
        if docker and docker.available:
            return SandboxBackend.DOCKER

        return SandboxBackend.NONE

    def _active_boundaries(self) -> list[str]:
        boundaries = [
            "command_policy",
            "filesystem_boundary",
            "network_policy",
            "audit_log",
        ]
        return boundaries

    def _audit(self, plan: SandboxPlan) -> None:
        available_names = [
            cap.backend.value for cap in plan.capabilities if cap.available
        ]
        self.audit_logger.write(
            AuditEvent(
                type="sandbox_status_checked",
                timestamp=utc_now_iso(),
                status="success",
                message=f"Sandbox status checked. Recommended: {plan.recommended_backend.value}.",
                metadata={
                    "platform": plan.platform,
                    "recommended_backend": plan.recommended_backend.value,
                    "available_backends": ",".join(available_names),
                },
            )
        )
