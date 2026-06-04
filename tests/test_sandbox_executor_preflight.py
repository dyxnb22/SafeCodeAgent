"""Tests for v3.11.2 sandbox executor preflight."""

from __future__ import annotations

from typer.testing import CliRunner

from safecode.audit.logger import AuditLogger
from safecode.cli import app
from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import DockerSandboxAdapter, SandboxExecutionRequest
from safecode.sandbox.approvals import SandboxExecutionApprovalStore
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability, SandboxCapabilityDetector
from safecode.sandbox.execution import SandboxExecutionGate
from safecode.sandbox.executor_preflight import (
    SandboxExecutorPreflight,
    has_executor_preflight_pass,
    normalize_executor_backend,
    real_execution_enabled,
)


def _anchor_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(tmp_path.parent / f"anchors-{tmp_path.name}"))


def _approval_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(tmp_path.parent / f"approvals-{tmp_path.name}"))


def _mock_capability(monkeypatch, backend: SandboxBackend, available: bool = True) -> None:
    def patched(self):
        return [
            SandboxCapability(
                backend=SandboxBackend.NONE,
                available=True,
                supported_platforms=["all"],
                reason="noop",
            ),
            SandboxCapability(
                backend=backend,
                available=available,
                supported_platforms=["test"],
                reason="mocked",
                network_isolation_supported=available,
                filesystem_isolation_supported=available,
                process_isolation_supported=available,
            ),
        ]

    monkeypatch.setattr(SandboxCapabilityDetector, "detect_all", patched)


def test_backend_aliases_are_supported() -> None:
    assert normalize_executor_backend("noop") == SandboxBackend.NONE
    assert normalize_executor_backend("seatbelt") == SandboxBackend.MACOS_SEATBELT
    assert normalize_executor_backend("bubblewrap") == SandboxBackend.LINUX_BUBBLEWRAP
    assert normalize_executor_backend("docker") == SandboxBackend.DOCKER


def test_noop_executor_preflight_passes_and_records(tmp_path, monkeypatch) -> None:
    _anchor_env(tmp_path, monkeypatch)
    result = SandboxExecutorPreflight(tmp_path).run("noop")

    assert result.passed is True
    assert result.promotion_state == "policy-gated"
    assert has_executor_preflight_pass(tmp_path, "noop") is True
    events = AuditLogger(tmp_path).read_recent(limit=5)
    assert any(event.type == "sandbox_executor_preflight_checked" for event in events)


def test_docker_unavailable_remains_preview(tmp_path, monkeypatch) -> None:
    _anchor_env(tmp_path, monkeypatch)
    _mock_capability(monkeypatch, SandboxBackend.DOCKER, available=False)

    result = SandboxExecutorPreflight(tmp_path).run("docker")

    assert result.passed is False
    assert result.promotion_state == "preview"
    assert has_executor_preflight_pass(tmp_path, "docker") is False


def test_docker_preflight_pass_plus_env_enables_real_execution(tmp_path, monkeypatch) -> None:
    _anchor_env(tmp_path, monkeypatch)
    _mock_capability(monkeypatch, SandboxBackend.DOCKER, available=True)
    result = SandboxExecutorPreflight(tmp_path).run("docker")
    monkeypatch.setenv("SAFECODE_SANDBOX_DOCKER", "1")

    enabled, reason = real_execution_enabled(tmp_path, "docker")

    assert result.passed is True
    assert enabled is True
    assert "enabled" in reason


def test_real_backend_requires_env_opt_in_before_approval_claim(tmp_path, monkeypatch) -> None:
    _anchor_env(tmp_path, monkeypatch)
    _approval_env(tmp_path, monkeypatch)
    _mock_capability(monkeypatch, SandboxBackend.DOCKER, available=True)
    cap = SandboxCapability(
        backend=SandboxBackend.DOCKER,
        available=True,
        supported_platforms=["test"],
        reason="mocked",
    )
    gate = SandboxExecutionGate(tmp_path, SafeCodeConfig())
    adapter = DockerSandboxAdapter(cap, tmp_path, SafeCodeConfig())
    plan = adapter.build_plan(
        SandboxExecutionRequest(
            command=["echo", "hello"],
            cwd=tmp_path,
            purpose="test",
            allow_network=False,
            readonly_filesystem=True,
        )
    )
    proposal = gate.propose(plan, "test")
    gate.approve()
    SandboxExecutorPreflight(tmp_path).run("docker")

    result = gate.execute_pending()

    assert result.executed is False
    assert "SAFECODE_SANDBOX_DOCKER=1" in result.message
    approval = SandboxExecutionApprovalStore(tmp_path).load_approval(proposal.proposal_id)
    assert approval is not None
    assert approval.consumed is False


def test_cli_executor_preflight_noop(tmp_path, monkeypatch) -> None:
    _anchor_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["sandbox", "executor-preflight", "noop"])

    assert result.exit_code == 0
    assert "policy-gated" in result.output
