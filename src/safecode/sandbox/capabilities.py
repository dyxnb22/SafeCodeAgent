"""OS sandbox capability detection.

Detects which sandbox backends are available on the current system,
without launching any processes or containers.
"""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass, field
from enum import Enum


class SandboxBackend(str, Enum):
    """Available sandbox backends ordered by isolation strength."""

    NONE = "none"
    MACOS_SEATBELT = "macos_seatbelt"
    LINUX_BUBBLEWRAP = "linux_bubblewrap"
    DOCKER = "docker"


@dataclass(frozen=True)
class SandboxCapability:
    """Detected capability for one sandbox backend."""

    backend: SandboxBackend
    available: bool
    supported_platforms: list[str]
    reason: str
    network_isolation_supported: bool = False
    filesystem_isolation_supported: bool = False
    process_isolation_supported: bool = False
    recommended_for: str = ""
    limitations: list[str] = field(default_factory=list)


class SandboxCapabilityDetector:
    """Detect available sandbox backends without executing them.

    This is a detection-only layer. It does NOT start containers,
    launch sandbox profiles, or wrap subprocess calls.
    """

    def detect_all(self) -> list[SandboxCapability]:
        """Return capabilities for all known backends."""
        return [
            self._detect_none(),
            self._detect_macos_seatbelt(),
            self._detect_linux_bubblewrap(),
            self._detect_docker(),
        ]

    def _detect_none(self) -> SandboxCapability:
        return SandboxCapability(
            backend=SandboxBackend.NONE,
            available=True,
            supported_platforms=["all"],
            reason="Logical-only containment: relies on FilesystemBoundary, NetworkPolicy, "
            "CommandPolicy, and audit logging. No OS-level sandbox is active.",
            recommended_for="Development and learning environments where logical "
            "guardrails are sufficient.",
            limitations=[
                "No kernel-enforced isolation.",
                "Cannot prevent a compromised subprocess from accessing the network "
                "if the process itself has access.",
                "Relies entirely on SafeCode Agent's Python-level policy enforcement.",
            ],
        )

    def _detect_macos_seatbelt(self) -> SandboxCapability:
        is_macos = platform.system() == "Darwin"
        sandbox_exec = shutil.which("sandbox-exec") if is_macos else None
        available = is_macos and sandbox_exec is not None
        return SandboxCapability(
            backend=SandboxBackend.MACOS_SEATBELT,
            available=available,
            supported_platforms=["macOS"],
            reason=(
                "macOS Seatbelt (sandbox-exec) is available at "
                f"{sandbox_exec}."
                if available
                else (
                    "Not available: "
                    + (
                        f"running on {platform.system()}, "
                        if not is_macos
                        else "sandbox-exec command not found."
                    )
                )
            ),
            network_isolation_supported=available,
            filesystem_isolation_supported=available,
            process_isolation_supported=False,
            recommended_for=(
                "macOS environments needing filesystem and network containment."
                if available
                else ""
            ),
            limitations=(
                [
                    "Sandbox profile language (.sb) is complex and error-prone.",
                    "Modern macOS versions (15+) increasingly restrict sandbox-exec "
                    "for third-party use.",
                    "Not suitable for cross-platform projects.",
                    "Process isolation is limited; sandbox-exec cannot prevent "
                    "fork-bombs or resource exhaustion.",
                ]
                if available
                else ["macOS sandbox-exec is not available on this system."]
            ),
        )

    def _detect_linux_bubblewrap(self) -> SandboxCapability:
        is_linux = platform.system() == "Linux"
        bwrap = shutil.which("bwrap") if is_linux else None
        available = is_linux and bwrap is not None
        return SandboxCapability(
            backend=SandboxBackend.LINUX_BUBBLEWRAP,
            available=available,
            supported_platforms=["Linux"],
            reason=(
                f"Bubblewrap (bwrap) is available at {bwrap}."
                if available
                else (
                    "Not available: "
                    + (
                        f"running on {platform.system()}, "
                        if not is_linux
                        else "bwrap command not found. Install with: apt install bubblewrap."
                    )
                )
            ),
            network_isolation_supported=available,
            filesystem_isolation_supported=available,
            process_isolation_supported=available,
            recommended_for=(
                "Linux environments needing strong, lightweight container-like isolation."
                if available
                else ""
            ),
            limitations=(
                [
                    "Requires user namespace support (CONFIG_USER_NS) in the kernel.",
                    "Not all distributions ship bubblewrap by default.",
                    "Nested sandboxing (bwrap inside bwrap) may not work.",
                ]
                if available
                else ["Bubblewrap is not installed or not supported on this system."]
            ),
        )

    def _detect_docker(self) -> SandboxCapability:
        docker_bin = shutil.which("docker")
        available = docker_bin is not None
        return SandboxCapability(
            backend=SandboxBackend.DOCKER,
            available=available,
            supported_platforms=["Linux", "macOS", "Windows"],
            reason=(
                f"Docker CLI is available at {docker_bin}."
                if available
                else "Docker is not installed or not on PATH."
            ),
            network_isolation_supported=available,
            filesystem_isolation_supported=available,
            process_isolation_supported=available,
            recommended_for=(
                "Heavy isolation needs: CI/CD pipelines, untrusted code execution, "
                "multi-service testing."
                if available
                else ""
            ),
            limitations=(
                [
                    "Requires Docker daemon to be running.",
                    "Container startup adds latency (seconds vs milliseconds).",
                    "Image size and pull time may be prohibitive for quick tasks.",
                    "Filesystem sharing between host and container requires explicit configuration.",
                ]
                if available
                else ["Docker is not installed or the daemon is not running."]
            ),
        )
