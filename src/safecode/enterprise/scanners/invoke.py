"""Sandbox-proposal-gated scanner invocation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.sandbox.execution import SandboxExecutionGate
from safecode.sandbox.factory import SandboxAdapterFactory


class ScannerInvocationError(Exception):
    """Scanner invocation error."""


class ScannerApprovalRequiredError(ScannerInvocationError):
    """Raised when scanner execution lacks explicit approval."""


@dataclass(frozen=True)
class ScannerInvocationSpec:
    scanner: str
    argv: list[str]
    purpose: str = "scanner_run"
    approved: bool = False


def propose_scanner_invocation(project_root: Path, spec: ScannerInvocationSpec):
    if not spec.argv or any(not isinstance(part, str) for part in spec.argv):
        raise ScannerInvocationError("scanner argv must be a non-empty structured list")
    if ";" in " ".join(spec.argv) or "|" in " ".join(spec.argv):
        raise ScannerInvocationError("shell metacharacters are not allowed in scanner argv")
    config = SafeCodeConfig.load(project_root)
    plan = SandboxAdapterFactory(project_root, config).create_plan(
        command=list(spec.argv),
        purpose=spec.purpose,
        allow_network=False,
        readonly_filesystem=True,
    )
    gate = SandboxExecutionGate(project_root, config)
    return gate.propose(plan, spec.purpose)


def invoke_scanner(project_root: Path, spec: ScannerInvocationSpec):
    if not spec.approved:
        raise ScannerApprovalRequiredError("scanner invocation requires explicit approval")
    return propose_scanner_invocation(project_root, spec)
