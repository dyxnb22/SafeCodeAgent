"""Sandbox-proposal-gated CI scanner runner (v2.2.4-T1)."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from safecode.config import SafeCodeConfig
from safecode.context.redactor import redact_secrets
from safecode.sandbox.execution import SandboxExecutionGate, SandboxExecutionProposal
from safecode.sandbox.factory import SandboxAdapterFactory
from safecode.sandbox.filesystem import FilesystemBoundary

from safecode.enterprise.scanners.invoke import (
    ScannerApprovalRequiredError,
    ScannerInvocationError,
)

ALLOWED_SCANNERS = frozenset({"semgrep", "pip-audit", "pytest"})
NETWORK_ARGV_MARKERS = frozenset({"curl", "wget", "nc", "netcat", "ssh", "scp"})
_SHELL_METACHAR_RE = re.compile(r"[;&|`$<>()\\\"']|\$\(")
_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_OUTPUT_BYTES = 256 * 1024
CI_SCANNER_RESULT_SCHEMA_VERSION = "1.0"


class CiScannerError(Exception):
    """Base CI scanner runner error."""


class CiScannerApprovalRequiredError(CiScannerError, ScannerApprovalRequiredError):
    """Raised when scanner execution lacks explicit approval."""


class CiScannerModelTextError(CiScannerError):
    """Raised when model text would be converted into argv."""


class CiScannerSecurityError(CiScannerError):
    """Raised when invocation violates sandbox security boundaries."""


class CiScannerBoundsError(CiScannerError):
    """Raised when execution exceeds configured bounds."""


@dataclass(frozen=True)
class CiScannerInvocationSpec:
    """Typed scanner invocation; argv must be structured, never parsed from model text."""

    scanner: str
    argv: list[str]
    commit_sha: str
    tool_version: str
    policy_snapshot_id: str
    purpose: str = "ci_scanner_run"
    approved: bool = False


@dataclass(frozen=True)
class CiScannerRunResult:
    """Bounded scanner execution result."""

    schema_version: str
    scanner: str
    commit_sha: str
    tool_version: str
    policy_snapshot_id: str
    executed: bool
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    output_truncated: bool
    proposal_id: str | None
    message: str


class SubprocessRunFn(Protocol):
    def __call__(
        self,
        argv: list[str],
        *,
        cwd: Path,
        timeout: int,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]: ...


def reject_model_text_as_argv(model_text: str) -> None:
    """Model output is never execution authority."""
    normalized = model_text.strip()
    if normalized:
        raise CiScannerModelTextError("model text cannot be converted into scanner argv")


def build_scanner_argv(
    scanner: str,
    *,
    config_path: str | None = None,
    target: str = ".",
) -> list[str]:
    """Build structured argv for an allowlisted scanner name."""
    normalized = scanner.strip()
    if normalized not in ALLOWED_SCANNERS:
        raise CiScannerError(f"unsupported scanner: {scanner!r}")
    if normalized == "semgrep":
        return ["semgrep", "scan", "--json", "--config", config_path or "p/ci", target]
    if normalized == "pip-audit":
        return ["pip-audit", "--format", "json"]
    return ["python3", "-m", "pytest", "-q", target]


def _validate_commit_sha(commit_sha: str) -> str:
    normalized = commit_sha.strip()
    if not _COMMIT_SHA_RE.fullmatch(normalized):
        raise CiScannerSecurityError("commit SHA must be a pinned 40-character hex digest")
    return normalized.lower()


def _validate_structured_argv(argv: list[str]) -> list[str]:
    if not argv or any(not isinstance(part, str) or not part.strip() for part in argv):
        raise ScannerInvocationError("scanner argv must be a non-empty structured list")
    joined = " ".join(argv)
    if _SHELL_METACHAR_RE.search(joined):
        raise CiScannerSecurityError("shell metacharacters are not allowed in scanner argv")
    if argv[0].lower() in NETWORK_ARGV_MARKERS or any(
        part.lower() in NETWORK_ARGV_MARKERS for part in argv[1:]
    ):
        raise CiScannerSecurityError("network-capable commands are not allowed in scanner argv")
    return list(argv)


def _validate_workspace(project_root: Path, workspace_root: Path) -> Path:
    resolved = workspace_root.resolve()
    boundary = FilesystemBoundary(project_root)
    try:
        return boundary.validate(resolved)
    except PermissionError as exc:
        raise CiScannerSecurityError(str(exc)) from exc


def _bound_output(text: str, *, max_bytes: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated, True


class CiScannerRunner:
    """Execute allowlisted scanners through the sandbox proposal pipeline."""

    def __init__(
        self,
        project_root: Path,
        *,
        workspace_root: Path,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        run_fn: SubprocessRunFn | None = None,
    ) -> None:
        self.project_root = project_root
        self.workspace_root = _validate_workspace(project_root, workspace_root)
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self._run_fn = run_fn or _default_run_fn

    def propose(self, spec: CiScannerInvocationSpec) -> SandboxExecutionProposal:
        argv = self._prepare_spec(spec)
        config = SafeCodeConfig.load(self.project_root)
        try:
            plan = SandboxAdapterFactory(self.project_root, config).create_plan(
                command=argv,
                purpose=spec.purpose,
                allow_network=False,
                readonly_filesystem=True,
            )
            gate = SandboxExecutionGate(self.project_root, config)
            return gate.propose(plan, spec.purpose)
        except PermissionError as exc:
            raise CiScannerSecurityError(str(exc)) from exc

    def run(self, spec: CiScannerInvocationSpec) -> CiScannerRunResult:
        if not spec.approved:
            raise CiScannerApprovalRequiredError("ci scanner invocation requires explicit approval")
        argv = self._prepare_spec(spec)
        proposal = self.propose(
            CiScannerInvocationSpec(
                scanner=spec.scanner,
                argv=argv,
                commit_sha=spec.commit_sha,
                tool_version=spec.tool_version,
                policy_snapshot_id=spec.policy_snapshot_id,
                purpose=spec.purpose,
                approved=True,
            )
        )
        started = time.monotonic()
        try:
            completed = self._run_fn(
                argv,
                cwd=self.workspace_root,
                timeout=self.timeout_seconds,
                capture_output=True,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            stdout, stdout_truncated = _bound_output(
                redact_secrets(completed.stdout or ""),
                max_bytes=self.max_output_bytes,
            )
            stderr, stderr_truncated = _bound_output(
                redact_secrets(completed.stderr or ""),
                max_bytes=self.max_output_bytes,
            )
            if stdout_truncated or stderr_truncated:
                raise CiScannerBoundsError("scanner output exceeds configured size limit")
            return CiScannerRunResult(
                schema_version=CI_SCANNER_RESULT_SCHEMA_VERSION,
                scanner=spec.scanner,
                commit_sha=spec.commit_sha,
                tool_version=spec.tool_version,
                policy_snapshot_id=spec.policy_snapshot_id,
                executed=True,
                exit_code=completed.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
                output_truncated=False,
                proposal_id=proposal.proposal_id,
                message=f"scanner completed with exit code {completed.returncode}",
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            raise CiScannerBoundsError(
                f"scanner execution timed out after {self.timeout_seconds}s"
            ) from exc
        except OSError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            stderr_clean = redact_secrets(str(exc))
            return CiScannerRunResult(
                schema_version=CI_SCANNER_RESULT_SCHEMA_VERSION,
                scanner=spec.scanner,
                commit_sha=spec.commit_sha,
                tool_version=spec.tool_version,
                policy_snapshot_id=spec.policy_snapshot_id,
                executed=False,
                exit_code=None,
                stdout="",
                stderr=stderr_clean,
                duration_ms=duration_ms,
                output_truncated=False,
                proposal_id=proposal.proposal_id,
                message=stderr_clean[:500],
            )

    def _prepare_spec(self, spec: CiScannerInvocationSpec) -> list[str]:
        commit_sha = _validate_commit_sha(spec.commit_sha)
        if spec.scanner not in ALLOWED_SCANNERS:
            raise CiScannerError(f"unsupported scanner: {spec.scanner!r}")
        argv = _validate_structured_argv(spec.argv)
        _ = commit_sha
        return argv


def _default_run_fn(
    argv: list[str],
    *,
    cwd: Path,
    timeout: int,
    capture_output: bool,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        timeout=timeout,
        capture_output=capture_output,
        text=True,
        check=False,
        shell=False,
    )
