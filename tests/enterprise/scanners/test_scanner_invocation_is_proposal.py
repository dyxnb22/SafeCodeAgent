"""Scanner invocation must go through sandbox proposal gate."""

from pathlib import Path

import pytest

from safecode.enterprise.scanners.invoke import (
    ScannerApprovalRequiredError,
    ScannerInvocationSpec,
    invoke_scanner,
    propose_scanner_invocation,
)


def test_scanner_invocation_requires_approval(tmp_path: Path):
    spec = ScannerInvocationSpec(scanner="semgrep", argv=["semgrep", "--config", "p/ci"], approved=False)
    with pytest.raises(ScannerApprovalRequiredError):
        invoke_scanner(tmp_path, spec)


def test_scanner_proposal_uses_structured_argv(tmp_path: Path):
    spec = ScannerInvocationSpec(scanner="semgrep", argv=["echo", "scan"], approved=True)
    proposal = propose_scanner_invocation(tmp_path, spec)
    assert proposal.command == ["echo", "scan"]
