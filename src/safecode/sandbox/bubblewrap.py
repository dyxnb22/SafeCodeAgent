"""Linux Bubblewrap (bwrap) argv plan generation.

Generates conservative bwrap arguments from a SandboxExecutionRequest.
This is argv preview only — bwrap is never invoked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import SandboxExecutionRequest
from safecode.sandbox.filesystem import FilesystemBoundary

SYSTEM_RO_BIND_PATHS = [
    "/usr",
    "/bin",
    "/lib",
    "/lib64",
    "/etc",
]

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
class BubblewrapArgsPlan:
    """Generated Bubblewrap argv plan."""

    argv: list[str]
    readonly_filesystem: bool
    network_enabled: bool
    bind_readonly_paths: list[str] = field(default_factory=list)
    bind_writable_paths: list[str] = field(default_factory=list)
    tmpfs_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BubblewrapArgsBuilder:
    """Build conservative Bubblewrap arguments from a request.

    Never invokes bwrap — this is preview-only generation.
    """

    def __init__(self, project_root: Path, config: SafeCodeConfig) -> None:
        self.project_root = project_root.resolve()
        self.config = config
        self.filesystem = FilesystemBoundary(project_root, config)
        self._sensitive = set(config.sandbox.sensitive_names) | SENSITIVE_SEGMENTS

    def build(self, request: SandboxExecutionRequest) -> BubblewrapArgsPlan:
        """Generate bwrap argv plan. Never executes bwrap."""
        warnings: list[str] = [
            "This is a development preview — bwrap args are not production-ready.",
            "Args are generated for review only. bwrap was NOT invoked.",
            "System paths are bound broadly; tighten for production use.",
        ]
        bind_ro: list[str] = []
        bind_rw: list[str] = []
        tmpfs: list[str] = []
        argv: list[str] = []

        project_str = str(self.project_root)

        argv.append("bwrap")
        argv.append("--die-with-parent")
        argv.append("--new-session")

        if not request.allow_network:
            argv.append("--unshare-net")
        else:
            warnings.append(
                "Network access is allowed in bwrap plan but not validated. "
                "v1.7.2 generates args only — no execution."
            )

        argv.append("--unshare-pid")
        argv.append("--unshare-ipc")
        argv.append("--unshare-uts")

        bind_ro.append(project_str)
        argv.append("--ro-bind")
        argv.append(project_str)
        argv.append(project_str)

        for sys_path in SYSTEM_RO_BIND_PATHS:
            if Path(sys_path).exists():
                bind_ro.append(sys_path)
                argv.append("--ro-bind")
                argv.append(sys_path)
                argv.append(sys_path)

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
                    bind_rw.append(resolved_str)
                    argv.append("--bind")
                    argv.append(resolved_str)
                    argv.append(resolved_str)
            except PermissionError:
                warnings.append(f"Writable path rejected by FilesystemBoundary: {path}")

        tmpfs_path = "/tmp"
        tmpfs.append(tmpfs_path)
        argv.append("--tmpfs")
        argv.append(tmpfs_path)

        argv.append("--")
        argv.extend(request.command)

        return BubblewrapArgsPlan(
            argv=argv,
            readonly_filesystem=request.readonly_filesystem,
            network_enabled=request.allow_network,
            bind_readonly_paths=bind_ro,
            bind_writable_paths=bind_rw,
            tmpfs_paths=tmpfs,
            denied_paths=[],
            warnings=warnings,
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
