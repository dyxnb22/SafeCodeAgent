"""Sandbox adapter contract for v1.7.0.

Defines the abstract interface for OS-level sandbox backends. All adapters
in this version are dry-run only: they build execution plans but never
launch external processes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability


@dataclass(frozen=True)
class SandboxExecutionRequest:
    """Request to run a command inside a sandbox."""

    command: list[str]
    cwd: Path
    purpose: str = "shell"
    allow_network: bool = False
    readonly_filesystem: bool = True
    writable_paths: list[Path] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30


@dataclass(frozen=True)
class SandboxExecutionPlan:
    """A dry-run plan describing how a command would be sandboxed."""

    backend: SandboxBackend
    command: list[str]
    cwd: str
    network_enabled: bool
    readonly_filesystem: bool
    writable_paths: list[str]
    env_keys: list[str]
    timeout_seconds: int
    dry_run: bool = True
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


class SandboxAdapter(Protocol):
    """Protocol for sandbox backend adapters."""

    def build_plan(self, request: SandboxExecutionRequest) -> SandboxExecutionPlan:
        """Build a dry-run execution plan. Must not execute anything."""
        ...

    def supports_execution(self) -> bool:
        """Whether this adapter can actually execute commands."""
        ...

    @property
    def backend(self) -> SandboxBackend:
        """The backend this adapter targets."""
        ...


class NoopSandboxAdapter:
    """Adapter that always produces a dry-run plan with no OS sandbox."""

    backend = SandboxBackend.NONE

    def build_plan(self, request: SandboxExecutionRequest) -> SandboxExecutionPlan:
        return SandboxExecutionPlan(
            backend=SandboxBackend.NONE,
            command=list(request.command),
            cwd=str(request.cwd),
            network_enabled=request.allow_network,
            readonly_filesystem=request.readonly_filesystem,
            writable_paths=[str(p) for p in request.writable_paths],
            env_keys=sorted(request.env.keys()),
            timeout_seconds=request.timeout_seconds,
            warnings=[
                "No OS-level sandbox is active.",
                "Execution relies on SafeCode logical boundaries only.",
            ],
            limitations=[
                "No kernel-enforced isolation.",
                "Network access depends entirely on NetworkPolicy.",
                "Filesystem access depends entirely on FilesystemBoundary.",
            ],
        )

    def supports_execution(self) -> bool:
        return False


class MacOSSeatbeltAdapter:
    """Adapter for macOS sandbox-exec. Dry-run only in v1.7.0."""

    def __init__(self, capability: SandboxCapability) -> None:
        self._capability = capability

    backend = SandboxBackend.MACOS_SEATBELT

    def build_plan(self, request: SandboxExecutionRequest) -> SandboxExecutionPlan:
        warnings = list(self._capability.limitations) if self._capability.limitations else []
        writable = [str(p) for p in request.writable_paths]
        return SandboxExecutionPlan(
            backend=SandboxBackend.MACOS_SEATBELT,
            command=list(request.command),
            cwd=str(request.cwd),
            network_enabled=request.allow_network,
            readonly_filesystem=request.readonly_filesystem,
            writable_paths=writable,
            env_keys=sorted(request.env.keys()),
            timeout_seconds=request.timeout_seconds,
            warnings=warnings + [
                "macOS sandbox-exec requires a .sb profile that is not generated in v1.7.0.",
            ],
            limitations=[
                "v1.7.0 does not execute sandbox-exec.",
                "Sandbox profile generation is deferred to a future version.",
            ],
        )

    def supports_execution(self) -> bool:
        return False


class LinuxBubblewrapAdapter:
    """Adapter for Linux bubblewrap. Dry-run only in v1.7.0."""

    def __init__(self, capability: SandboxCapability) -> None:
        self._capability = capability

    backend = SandboxBackend.LINUX_BUBBLEWRAP

    def build_plan(self, request: SandboxExecutionRequest) -> SandboxExecutionPlan:
        warnings = list(self._capability.limitations) if self._capability.limitations else []
        writable = [str(p) for p in request.writable_paths]
        return SandboxExecutionPlan(
            backend=SandboxBackend.LINUX_BUBBLEWRAP,
            command=list(request.command),
            cwd=str(request.cwd),
            network_enabled=request.allow_network,
            readonly_filesystem=request.readonly_filesystem,
            writable_paths=writable,
            env_keys=sorted(request.env.keys()),
            timeout_seconds=request.timeout_seconds,
            warnings=warnings + [
                "bwrap requires user namespace support in the kernel.",
                "v1.7.0 does not execute bwrap.",
            ],
            limitations=[
                "v1.7.0 does not execute bubblewrap.",
                "Actual bwrap argument construction is deferred to a future version.",
            ],
        )

    def supports_execution(self) -> bool:
        return False


class DockerSandboxAdapter:
    """Adapter for Docker. Dry-run only in v1.7.0."""

    def __init__(self, capability: SandboxCapability) -> None:
        self._capability = capability

    backend = SandboxBackend.DOCKER

    def build_plan(self, request: SandboxExecutionRequest) -> SandboxExecutionPlan:
        warnings = list(self._capability.limitations) if self._capability.limitations else []
        writable = [str(p) for p in request.writable_paths]
        return SandboxExecutionPlan(
            backend=SandboxBackend.DOCKER,
            command=list(request.command),
            cwd=str(request.cwd),
            network_enabled=request.allow_network,
            readonly_filesystem=request.readonly_filesystem,
            writable_paths=writable,
            env_keys=sorted(request.env.keys()),
            timeout_seconds=request.timeout_seconds,
            warnings=warnings + [
                "Docker daemon must be running for actual execution.",
                "v1.7.0 does not execute docker.",
            ],
            limitations=[
                "v1.7.0 does not execute Docker containers.",
                "Container image selection and volume mounting are deferred.",
            ],
        )

    def supports_execution(self) -> bool:
        return False
