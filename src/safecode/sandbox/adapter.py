"""Sandbox adapter contract for v1.7.0.

Defines the abstract interface for OS-level sandbox backends. All adapters
in this version are dry-run only: they build execution plans but never
launch external processes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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
    profile_preview: str | None = None
    profile_backend: str | None = None
    profile_warnings: list[str] = field(default_factory=list)
    args_preview: list[str] = field(default_factory=list)
    args_backend: str | None = None
    args_warnings: list[str] = field(default_factory=list)


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
    """Adapter for macOS sandbox-exec. Dry-run only — generates profile preview."""

    def __init__(self, capability: SandboxCapability, project_root: Path | None = None, config=None) -> None:
        self._capability = capability
        self._project_root = project_root
        self._config = config

    backend = SandboxBackend.MACOS_SEATBELT

    def build_plan(self, request: SandboxExecutionRequest) -> SandboxExecutionPlan:
        from safecode.sandbox.seatbelt import SeatbeltProfileBuilder
        from safecode.config import SafeCodeConfig

        adapter_warnings = list(self._capability.limitations) if self._capability.limitations else []
        cfg = self._config if self._config else SafeCodeConfig()
        effective_request = request
        if request.allow_network and not cfg.sandbox.network_enabled:
            effective_request = replace(request, allow_network=False)
            adapter_warnings.append("Network access was requested but disabled by SafeCodeConfig.")
        writable = [str(p) for p in request.writable_paths]

        profile_preview = None
        profile_backend = None
        profile_warnings: list[str] = []

        if self._project_root is not None:
            profile_plan = SeatbeltProfileBuilder(self._project_root, cfg).build(effective_request)
            profile_preview = profile_plan.profile_text
            profile_backend = "macos_seatbelt"
            profile_warnings = list(profile_plan.warnings)
            writable = list(profile_plan.allowed_write_paths)

        return SandboxExecutionPlan(
            backend=SandboxBackend.MACOS_SEATBELT,
            command=list(effective_request.command),
            cwd=str(effective_request.cwd),
            network_enabled=effective_request.allow_network,
            readonly_filesystem=effective_request.readonly_filesystem,
            writable_paths=writable,
            env_keys=sorted(effective_request.env.keys()),
            timeout_seconds=effective_request.timeout_seconds,
            warnings=adapter_warnings + [
                "macOS sandbox-exec profile is generated for preview only.",
            ],
            limitations=[
                "v1.7.1 does not execute sandbox-exec.",
                "Profile is for review purposes only.",
            ],
            profile_preview=profile_preview,
            profile_backend=profile_backend,
            profile_warnings=profile_warnings,
        )

    def supports_execution(self) -> bool:
        return False


class LinuxBubblewrapAdapter:
    """Adapter for Linux bubblewrap. Dry-run only — generates argv preview."""

    def __init__(self, capability: SandboxCapability, project_root: Path | None = None, config=None) -> None:
        self._capability = capability
        self._project_root = project_root
        self._config = config

    backend = SandboxBackend.LINUX_BUBBLEWRAP

    def build_plan(self, request: SandboxExecutionRequest) -> SandboxExecutionPlan:
        from safecode.sandbox.bubblewrap import BubblewrapArgsBuilder
        from safecode.config import SafeCodeConfig

        adapter_warnings = list(self._capability.limitations) if self._capability.limitations else []
        cfg = self._config if self._config else SafeCodeConfig()
        effective_request = request
        if request.allow_network and not cfg.sandbox.network_enabled:
            effective_request = replace(request, allow_network=False)
            adapter_warnings.append("Network access was requested but disabled by SafeCodeConfig.")
        writable = [str(p) for p in request.writable_paths]

        args_preview: list[str] = []
        args_backend = None
        args_warnings: list[str] = []

        if self._project_root is not None:
            bwrap_plan = BubblewrapArgsBuilder(self._project_root, cfg).build(effective_request)
            args_preview = list(bwrap_plan.argv)
            args_backend = "linux_bubblewrap"
            args_warnings = list(bwrap_plan.warnings)
            writable = list(bwrap_plan.bind_writable_paths)

        return SandboxExecutionPlan(
            backend=SandboxBackend.LINUX_BUBBLEWRAP,
            command=list(effective_request.command),
            cwd=str(effective_request.cwd),
            network_enabled=effective_request.allow_network,
            readonly_filesystem=effective_request.readonly_filesystem,
            writable_paths=writable,
            env_keys=sorted(effective_request.env.keys()),
            timeout_seconds=effective_request.timeout_seconds,
            warnings=adapter_warnings + [
                "bwrap requires user namespace support in the kernel.",
                "v1.7.2 generates bwrap args for preview only.",
            ],
            limitations=[
                "v1.7.2 does not execute bubblewrap.",
                "Args are for review purposes only.",
            ],
            args_preview=args_preview,
            args_backend=args_backend,
            args_warnings=args_warnings,
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
