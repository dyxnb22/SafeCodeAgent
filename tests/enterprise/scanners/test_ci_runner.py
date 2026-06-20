"""Tests for sandboxed CI scanner runner (v2.2.4-T1)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from safecode.enterprise.scanners.ci_runner import (
    CiScannerApprovalRequiredError,
    CiScannerBoundsError,
    CiScannerError,
    CiScannerInvocationSpec,
    CiScannerModelTextError,
    CiScannerRunner,
    CiScannerSecurityError,
    build_scanner_argv,
    reject_model_text_as_argv,
)

COMMIT_SHA = "a" * 40
POLICY_SNAPSHOT = "snapshot-test"


def _spec(
    *,
    scanner: str = "semgrep",
    argv: list[str] | None = None,
    approved: bool = True,
) -> CiScannerInvocationSpec:
    return CiScannerInvocationSpec(
        scanner=scanner,
        argv=argv or build_scanner_argv(scanner),
        commit_sha=COMMIT_SHA,
        tool_version="1.0.0",
        policy_snapshot_id=POLICY_SNAPSHOT,
        approved=approved,
    )


def test_approved_structured_argv_runs_deterministic_fixture(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("print('ok')\n", encoding="utf-8")

    def run_fn(argv, *, cwd, timeout, capture_output):
        assert argv == ["echo", "scanner-ok"]
        assert cwd == workspace
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    runner = CiScannerRunner(
        tmp_path,
        workspace_root=workspace,
        run_fn=run_fn,
    )
    result = runner.run(
        _spec(
            scanner="semgrep",
            argv=["echo", "scanner-ok"],
        )
    )
    assert result.executed is True
    assert result.exit_code == 0
    assert result.stdout == "{}"
    assert result.proposal_id


def test_runner_refuses_without_approval(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runner = CiScannerRunner(tmp_path, workspace_root=workspace)
    with pytest.raises(CiScannerApprovalRequiredError):
        runner.run(_spec(approved=False))


def test_model_text_never_becomes_argv():
    with pytest.raises(CiScannerModelTextError):
        reject_model_text_as_argv("semgrep --config p/ci; curl evil.example")


def test_build_scanner_argv_rejects_unknown_scanner():
    with pytest.raises(CiScannerError):
        build_scanner_argv("bash")


def test_shell_metacharacters_rejected(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runner = CiScannerRunner(tmp_path, workspace_root=workspace)
    with pytest.raises(CiScannerSecurityError):
        runner.run(_spec(argv=["echo", "ok; rm -rf /"]))


def test_network_command_rejected(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runner = CiScannerRunner(tmp_path, workspace_root=workspace)
    with pytest.raises(CiScannerSecurityError):
        runner.run(_spec(argv=["curl", "https://example.com"]))


def test_timeout_fails_closed(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def slow_run(argv, *, cwd, timeout, capture_output):
        raise subprocess.TimeoutExpired(argv, timeout)

    runner = CiScannerRunner(
        tmp_path,
        workspace_root=workspace,
        timeout_seconds=1,
        run_fn=slow_run,
    )
    with pytest.raises(CiScannerBoundsError, match="timed out"):
        runner.run(_spec(argv=["echo", "slow"]))


def test_output_overflow_fails_closed(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def noisy_run(argv, *, cwd, timeout, capture_output):
        return subprocess.CompletedProcess(argv, 0, stdout="x" * 300_000, stderr="")

    runner = CiScannerRunner(
        tmp_path,
        workspace_root=workspace,
        max_output_bytes=1024,
        run_fn=noisy_run,
    )
    with pytest.raises(CiScannerBoundsError, match="output exceeds"):
        runner.run(_spec(argv=["echo", "overflow"]))


def test_workspace_escape_rejected(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(CiScannerSecurityError, match="escapes project root"):
        CiScannerRunner(project_root, workspace_root=outside)


def test_runner_redacts_output_before_storage(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = "ghp_1234567890123456789012345678901234"

    def run_fn(argv, *, cwd, timeout, capture_output):
        return subprocess.CompletedProcess(
            argv,
            1,
            stdout=f"finding included token {secret}",
            stderr=f"error: token {secret}",
        )

    runner = CiScannerRunner(
        tmp_path,
        workspace_root=workspace,
        run_fn=run_fn,
    )
    result = runner.run(_spec(argv=["echo", "fail"]))
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert secret not in result.message


def test_propose_creates_sandbox_proposal(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runner = CiScannerRunner(tmp_path, workspace_root=workspace)
    proposal = runner.propose(
        _spec(
            scanner="semgrep",
            argv=["echo", "scan"],
            approved=False,
        )
    )
    assert proposal.command == ["echo", "scan"]
    assert proposal.network_enabled is False
    assert proposal.readonly_filesystem is True
