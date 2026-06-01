"""Docker container plan generation and execution for v2.4.0.

DockerContainerPlanBuilder generates conservative docker run arguments.
DockerDaemonChecker verifies the Docker daemon is reachable.
DockerExecutor rebuilds the plan from a stored proposal and runs it.
No shell=True is ever used.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import SandboxExecutionRequest
from safecode.sandbox.filesystem import FilesystemBoundary

if TYPE_CHECKING:
    from safecode.sandbox.execution import SandboxExecutionProposal

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
            "Args are generated for review; execution requires proposal approval.",
            f"Image {DEFAULT_IMAGE} is a preview default and not configurable in v2.4.0.",
        ]
        limitations: list[str] = [
            "Container image selection is not configurable in v2.4.0.",
            "Docker daemon is checked at execution time, not plan time.",
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
                "Docker execution will require approval and daemon availability."
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


# ── v2.4.0: Docker execution ──────────────────────────────────────────────


@dataclass(frozen=True)
class DockerExecutionResult:
    """Result of a Docker execution attempt."""

    executed: bool
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    message: str


class DockerDaemonChecker:
    """Check whether the Docker daemon is reachable.

    Uses ``docker info`` with a short timeout. Injectable ``run_fn`` lets
    tests substitute a fake without a real Docker daemon.
    """

    _TIMEOUT_SECONDS = 5
    _INFO_ARGV = ["docker", "info", "--format", "{{.ServerVersion}}"]

    def __init__(self, run_fn: Callable[..., Any] | None = None) -> None:
        self._run = run_fn

    def check(self) -> tuple[bool, str]:
        """Return ``(available, reason)``. Never raises."""
        run = self._run or subprocess.run
        try:
            result = run(
                self._INFO_ARGV,
                capture_output=True,
                timeout=self._TIMEOUT_SECONDS,
                shell=False,
            )
            if result.returncode == 0:
                return True, ""
            return False, f"Docker daemon not reachable (exit {result.returncode})."
        except FileNotFoundError:
            return False, "docker CLI not found in PATH."
        except subprocess.TimeoutExpired:
            return False, f"Docker daemon did not respond within {self._TIMEOUT_SECONDS}s."
        except OSError as exc:
            return False, f"Docker daemon check failed: {exc}"
        except Exception as exc:
            return False, f"Docker daemon check failed: {exc}"


class DockerExecutor:
    """Execute a pending sandbox proposal via Docker for v2.4.0.

    Reconstructs the Docker run argv from the stored proposal fields,
    verifies the preview hash, checks daemon availability, then runs the
    container using ``subprocess.run`` with ``shell=False``.

    Injectable ``daemon_checker`` and ``run_fn`` allow full testing
    without a real Docker daemon.
    """

    def __init__(
        self,
        project_root: Path,
        config: SafeCodeConfig,
        daemon_checker: DockerDaemonChecker | None = None,
        run_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.project_root = project_root
        self.config = config
        self._daemon_checker = daemon_checker or DockerDaemonChecker()
        self._run = run_fn or subprocess.run

    def execute(self, proposal: SandboxExecutionProposal) -> DockerExecutionResult:
        """Rebuild plan, verify hash, check daemon, then run. Never raises."""
        start_ms = int(time.monotonic() * 1000)

        request = SandboxExecutionRequest(
            command=list(proposal.command),
            cwd=Path(proposal.cwd),
            purpose=proposal.purpose,
            allow_network=proposal.network_enabled,
            readonly_filesystem=proposal.readonly_filesystem,
            writable_paths=[Path(p) for p in proposal.writable_paths],
            env={},
            timeout_seconds=30,
        )
        plan = DockerContainerPlanBuilder(self.project_root, self.config).build(request)

        # Verify that the rebuilt argv matches the hash the user approved.
        if proposal.preview_hash is not None:
            actual_hash = hashlib.sha256(
                json.dumps(plan.argv, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if actual_hash != proposal.preview_hash:
                msg = (
                    "Docker argv hash mismatch — container plan changed since "
                    "the proposal was created."
                )
                return DockerExecutionResult(
                    executed=False,
                    exit_code=None,
                    stdout="",
                    stderr=msg,
                    duration_ms=int(time.monotonic() * 1000) - start_ms,
                    message=msg,
                )

        available, reason = self._daemon_checker.check()
        if not available:
            msg = f"Docker daemon unavailable: {reason}"
            return DockerExecutionResult(
                executed=False,
                exit_code=None,
                stdout="",
                stderr=msg,
                duration_ms=int(time.monotonic() * 1000) - start_ms,
                message=msg,
            )

        timeout = 30
        try:
            proc = self._run(
                plan.argv,
                capture_output=True,
                timeout=timeout,
                shell=False,
            )
            elapsed_ms = int(time.monotonic() * 1000) - start_ms
            stdout = (
                proc.stdout.decode("utf-8", errors="replace")
                if isinstance(proc.stdout, bytes)
                else (proc.stdout or "")
            )
            stderr = (
                proc.stderr.decode("utf-8", errors="replace")
                if isinstance(proc.stderr, bytes)
                else (proc.stderr or "")
            )
            return DockerExecutionResult(
                executed=True,
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_ms=elapsed_ms,
                message=f"Docker execution completed. Exit code: {proc.returncode}.",
            )
        except subprocess.TimeoutExpired:
            msg = f"Docker execution timed out after {timeout}s."
            return DockerExecutionResult(
                executed=False,
                exit_code=None,
                stdout="",
                stderr=msg,
                duration_ms=int(time.monotonic() * 1000) - start_ms,
                message=msg,
            )
        except OSError as exc:
            msg = f"Docker execution failed: {exc}"
            return DockerExecutionResult(
                executed=False,
                exit_code=None,
                stdout="",
                stderr=msg,
                duration_ms=int(time.monotonic() * 1000) - start_ms,
                message=msg,
            )
        except Exception as exc:
            msg = f"Docker execution failed: {exc}"
            return DockerExecutionResult(
                executed=False,
                exit_code=None,
                stdout="",
                stderr=msg,
                duration_ms=int(time.monotonic() * 1000) - start_ms,
                message=msg,
            )
