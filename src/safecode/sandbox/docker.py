"""Docker container plan generation.

Generates conservative docker run arguments from a SandboxExecutionRequest.
This is argv preview only — docker is never invoked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import SandboxExecutionRequest
from safecode.sandbox.filesystem import FilesystemBoundary

DEFAULT_IMAGE = "python:3.12-slim"

BLOCKED_WRITABLE_ROOTS = {
    "/home",
    "/tmp",
    "/var",
    "/private",
    "/root",
}

SENSITIVE_SEGMENTS = {
    ".env",
    ".ssh",
    ".aws",
    "id_rsa",
    "id_dsa",
    "credentials",
    "token",
    "secret",
    "password",
    ".pem",
    ".key",
    ".p12",
}


@dataclass(frozen=True)
class DockerContainerPlan:
    """Generated Docker container plan."""

    argv: list[str]
    image: str
    network_enabled: bool
    readonly_filesystem: bool
    readonly_mounts: list[str] = field(default_factory=list)
    writable_mounts: list[str] = field(default_factory=list)
    tmpfs_mounts: list[str] = field(default_factory=list)
    env_keys: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


class DockerContainerPlanBuilder:
    """Build conservative Docker run arguments from a request.

    Never invokes docker — this is preview-only generation.
    """

    def __init__(self, project_root: Path, config: SafeCodeConfig) -> None:
        self.project_root = project_root.resolve()
        self.config = config
        self.filesystem = FilesystemBoundary(project_root, config)
        self._sensitive = set(config.sandbox.sensitive_names) | SENSITIVE_SEGMENTS

    def build(self, request: SandboxExecutionRequest) -> DockerContainerPlan:
        """Generate docker run argv plan. Never executes docker."""
        warnings: list[str] = [
            "This is a development preview — docker args are not production-ready.",
            "Args are generated for review only. docker was NOT invoked.",
            f"Image {DEFAULT_IMAGE} is a preview default and not configurable in v1.7.3.",
        ]
        limitations: list[str] = [
            "v1.7.3 does not execute Docker containers.",
            "Container image selection is not configurable.",
            "Docker daemon is not checked for availability at plan time.",
        ]
        ro_mounts: list[str] = []
        rw_mounts: list[str] = []
        tmpfs: list[str] = []
        argv: list[str] = []

        project_str = str(self.project_root)

        argv.append("docker")
        argv.append("run")
        argv.append("--rm")
        argv.append("--init")
        argv.append("--workdir")
        argv.append(project_str)

        if not request.allow_network:
            argv.append("--network")
            argv.append("none")
        else:
            warnings.append(
                "Network access is allowed in docker plan but not validated. "
                "v1.7.3 generates args only — no execution."
            )

        if request.readonly_filesystem:
            argv.append("--read-only")

        mount_arg = f"type=bind,src={project_str},dst={project_str},readonly"
        ro_mounts.append(project_str)
        argv.append("--mount")
        argv.append(mount_arg)

        for path in request.writable_paths:
            try:
                resolved = self.filesystem.validate(path)
                resolved_str = str(resolved)
                if not request.readonly_filesystem:
                    if self._is_sensitive_path(resolved):
                        warnings.append(
                            f"Writable path {path} includes a sensitive segment; "
                            "will not grant write access."
                        )
                        continue
                    if not self._path_starts_with(resolved, self.project_root):
                        warnings.append(
                            f"Writable path {path} is outside project root; "
                            "will not grant write access."
                        )
                        continue
                    root = self._blocked_writable_root(resolved_str)
                    if root:
                        warnings.append(
                            f"Writable path {path} falls under blocked root {root}; "
                            "will not grant write access."
                        )
                        continue
                    if self._has_unsafe_mount_chars(resolved_str):
                        warnings.append(
                            f"Writable path {path} contains characters unsafe for Docker --mount preview; "
                            "will not grant write access."
                        )
                        continue
                    rw_mounts.append(resolved_str)
                    rw_mount_arg = f"type=bind,src={resolved_str},dst={resolved_str}"
                    argv.append("--mount")
                    argv.append(rw_mount_arg)
            except PermissionError:
                warnings.append(f"Writable path rejected by FilesystemBoundary: {path}")

        tmpfs_opt = "/tmp:rw,noexec,nosuid,nodev"
        tmpfs.append(tmpfs_opt)
        argv.append("--tmpfs")
        argv.append(tmpfs_opt)

        argv.append(DEFAULT_IMAGE)
        argv.extend(request.command)

        return DockerContainerPlan(
            argv=argv,
            image=DEFAULT_IMAGE,
            network_enabled=request.allow_network,
            readonly_filesystem=request.readonly_filesystem,
            readonly_mounts=ro_mounts,
            writable_mounts=rw_mounts,
            tmpfs_mounts=tmpfs,
            env_keys=sorted(request.env.keys()),
            warnings=warnings,
            limitations=limitations,
        )

    def _is_sensitive_path(self, path: Path) -> bool:
        lowered_parts = {part.lower() for part in path.parts}
        lowered_name = path.name.lower()
        for sensitive in self._sensitive:
            lowered = sensitive.lower()
            if lowered in lowered_parts or lowered in lowered_name:
                return True
        return False

    @staticmethod
    def _path_starts_with(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    @staticmethod
    def _blocked_writable_root(path_str: str) -> str | None:
        for blocked in BLOCKED_WRITABLE_ROOTS:
            if path_str == blocked:
                return blocked
        return None

    @staticmethod
    def _has_unsafe_mount_chars(path_str: str) -> bool:
        return "," in path_str
