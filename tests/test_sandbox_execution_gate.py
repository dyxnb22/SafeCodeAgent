"""Sandbox execution gate tests for v1.7.5.

Verifies proposal lifecycle: create, persist, load, discard, and block.
All operations are dry-run only — no external commands are executed.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.audit.logger import AuditLogger
from safecode.config import SafeCodeConfig
from safecode.cli import app
from safecode.sandbox.adapter import SandboxBackend, SandboxExecutionPlan
from safecode.sandbox.execution import (
    SandboxExecutionGate,
    SandboxExecutionProposal,
    SandboxExecutionProposalStore,
)
from safecode.sandbox.factory import SandboxAdapterFactory

runner = CliRunner()


def _make_plan(**kwargs):
    defaults = {
        "backend": SandboxBackend.NONE,
        "command": ["echo", "hello"],
        "cwd": "/tmp/test",
        "network_enabled": False,
        "readonly_filesystem": True,
        "writable_paths": [],
        "env_keys": [],
        "timeout_seconds": 30,
        "profile_preview": None,
        "args_preview": [],
        "container_preview": [],
    }
    defaults.update(kwargs)
    return SandboxExecutionPlan(**defaults)


# ── proposal store tests ──────────────────────────────────────────────


class TestProposalStore:
    def test_create_writes_file(self, tmp_path):
        store = SandboxExecutionProposalStore(tmp_path)
        p = SandboxExecutionProposal(
            proposal_id="test-id",
            created_at="2026-01-01T00:00:00Z",
            backend="none",
            command=["echo", "hello"],
            command_hash="abc123",
            purpose="shell",
            cwd="/tmp",
            network_enabled=False,
            readonly_filesystem=True,
            writable_paths=[],
            env_keys=[],
            preview_kind="none",
            preview_hash=None,
        )
        store.create(p)
        assert store.path.exists()

    def test_duplicate_blocked(self, tmp_path):
        store = SandboxExecutionProposalStore(tmp_path)
        p = _make_proposal()
        store.create(p)
        with pytest.raises(FileExistsError, match="already exists"):
            store.create(p)

    def test_corrupt_pending_not_overwritten(self, tmp_path):
        store = SandboxExecutionProposalStore(tmp_path)
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("{not valid json", encoding="utf-8")
        p = _make_proposal()
        with pytest.raises(FileExistsError, match="corrupt"):
            store.create(p)

    def test_discard_removes_file(self, tmp_path):
        store = SandboxExecutionProposalStore(tmp_path)
        store.create(_make_proposal())
        assert store.discard_pending() is True
        assert not store.path.exists()

    def test_discard_without_pending_is_safe(self, tmp_path):
        store = SandboxExecutionProposalStore(tmp_path)
        assert store.discard_pending() is False

    def test_load_pending_returns_none_when_no_file(self, tmp_path):
        store = SandboxExecutionProposalStore(tmp_path)
        assert store.load_pending() is None


# ── execution gate tests ──────────────────────────────────────────────


class TestExecutionGate:
    def test_propose_creates_proposal(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        proposal = gate.propose(_make_plan(), "shell")
        assert gate.pending_path.exists()
        assert proposal.status == "pending"
        assert proposal.backend == "none"

    def test_proposal_has_required_fields(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        proposal = gate.propose(_make_plan(command=["pwd"], env_keys=["HOME"]), "shell")
        assert proposal.proposal_id
        assert proposal.created_at
        assert proposal.command_hash
        assert proposal.preview_kind
        assert proposal.env_keys == ["HOME"]

    def test_proposal_no_env_value(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        plan = _make_plan(env_keys=["SECRET_KEY"])
        proposal = gate.propose(plan, "shell")
        raw = gate.pending_path.read_text(encoding="utf-8")
        assert "secret_value" not in raw.lower()

    def test_discard_writes_audit(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        gate.discard()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        types = [e.type for e in events]
        assert "sandbox_execution_discarded" in types

    def test_execute_pending_refused_without_approval(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        result = gate.execute_pending()
        assert result.executed is False
        assert result.dry_run is True
        # v1.8.0: preflight blocks unapproved proposals via preflight reasons
        assert "Approval" in result.message

    def test_execute_pending_no_subprocess_when_unapproved(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "call", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: called.append(1))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        gate.execute_pending()
        # v1.8.0: still no subprocess — preflight blocks before ShellRunner
        assert len(called) == 0

    def test_execute_pending_writes_audit_blocked(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        types = [e.type for e in events]
        # v1.8.0: unified "sandbox_execution_blocked" event for all preflight blocks
        assert "sandbox_execution_blocked" in types

    def test_disallowed_command_plan_rejected(self, tmp_path):
        with pytest.raises(PermissionError):
            SandboxAdapterFactory(tmp_path).create_plan(["curl", "https://bad.com"])

    def test_allowlisted_command_plan_proposes(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        plan = SandboxAdapterFactory(tmp_path).create_plan(["echo", "hello"])
        gate = SandboxExecutionGate(tmp_path)
        proposal = gate.propose(plan, "shell")
        assert proposal.status == "pending"

    def test_audit_metadata_no_command_args(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(command=["echo", "hello"]), "shell")
        events = AuditLogger(tmp_path).read_recent(limit=5)
        created = [e for e in events if e.type == "sandbox_execution_proposed"]
        assert len(created) >= 1
        md = created[0].metadata
        assert md["command_head"] == "echo"
        assert "hello" not in str(md)

    def test_audit_metadata_no_env_values(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        plan = _make_plan(env_keys=["SECRET_TOKEN"])
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(plan, "shell")
        events = AuditLogger(tmp_path).read_recent(limit=5)
        created = [e for e in events if e.type == "sandbox_execution_proposed"]
        md = created[0].metadata
        assert "SECRET_TOKEN" not in str(md)


class TestSandboxExecutionCli:
    def test_cli_propose_git_status_creates_pending_without_subprocess(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "call", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: called.append(1))

        result = runner.invoke(app, ["sandbox", "propose", "git", "status"])

        assert result.exit_code == 0
        assert "No command was executed" in result.output
        assert (tmp_path / ".sac" / "pending_sandbox_execution.json").exists()
        assert len(called) == 0

    def test_cli_pending_shows_pending_proposal(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["sandbox", "propose", "git", "status"])

        result = runner.invoke(app, ["sandbox", "pending"])

        assert result.exit_code == 0
        assert "Pending Sandbox Execution Proposal" in result.output
        assert "git status" in result.output

    def test_cli_execute_blocked_without_approval(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["sandbox", "propose", "git", "status"])
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "call", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: called.append(1))

        result = runner.invoke(app, ["sandbox", "execute"])

        assert result.exit_code == 0
        # v1.8.0: blocked by preflight — approval missing
        assert "Blocked" in result.output or "no" in result.output.lower()
        assert len(called) == 0

    def test_cli_discard_removes_pending_proposal(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["sandbox", "propose", "git", "status"])

        result = runner.invoke(app, ["sandbox", "discard"])

        assert result.exit_code == 0
        assert "discarded" in result.output
        assert not (tmp_path / ".sac" / "pending_sandbox_execution.json").exists()


# ── helpers ───────────────────────────────────────────────────────────


def _make_proposal():
    return SandboxExecutionProposal(
        proposal_id="test-id",
        created_at="2026-01-01T00:00:00Z",
        backend="none",
        command=["echo", "hello"],
        command_hash="abc123",
        purpose="shell",
        cwd="/tmp",
        network_enabled=False,
        readonly_filesystem=True,
        writable_paths=[],
        env_keys=[],
        preview_kind="none",
        preview_hash=None,
    )


# ── v2.4.0 Docker gate regression tests ──────────────────────────────


class TestDockerExecutionGate:
    """v2.4.0: Noop path unchanged; Docker blocked when daemon unavailable."""

    def test_noop_still_executes_after_docker_support(self, tmp_path, monkeypatch):
        """Noop execution path is completely unchanged by Docker support addition."""
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")  # Noop backend (SandboxBackend.NONE)
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is True
        assert result.exit_code == 0

    def test_docker_backend_blocked_when_daemon_unavailable(self, tmp_path, monkeypatch):
        """Docker execution fails closed when daemon check returns unavailable."""
        from safecode.sandbox.capabilities import SandboxCapabilityDetector, SandboxCapability
        from safecode.sandbox.docker import DockerDaemonChecker, DockerContainerPlanBuilder
        from safecode.sandbox.adapter import SandboxExecutionRequest
        from safecode.config import SafeCodeConfig

        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = SandboxExecutionGate(tmp_path)

        # Build a real Docker plan for the proposal
        req = SandboxExecutionRequest(
            command=["echo", "hello"],
            cwd=tmp_path,
            purpose="shell",
            allow_network=False,
            readonly_filesystem=True,
            writable_paths=[],
            env={},
            timeout_seconds=30,
        )
        docker_plan_obj = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(req)
        plan = _make_plan(
            backend=SandboxBackend.DOCKER,
            container_preview=docker_plan_obj.argv,
            container_backend="docker",
        )
        gate.propose(plan, "shell")
        gate.approve()

        # Mock Docker CLI as available for preflight
        original_detect_all = SandboxCapabilityDetector.detect_all

        def patched_detect_all(self):
            caps = original_detect_all(self)
            return [
                SandboxCapability(
                    backend=SandboxBackend.DOCKER,
                    available=True,
                    supported_platforms=["all"],
                    reason="mocked",
                )
                if cap.backend == SandboxBackend.DOCKER
                else cap
                for cap in caps
            ]

        monkeypatch.setattr(SandboxCapabilityDetector, "detect_all", patched_detect_all)

        # Daemon is unreachable at execution time
        monkeypatch.setattr(
            DockerDaemonChecker,
            "check",
            lambda self: (False, "no daemon in test"),
        )

        result = gate.execute_pending()
        assert result.executed is False
        assert result.dry_run is True
        assert "unavailable" in result.message.lower()

    def test_docker_execution_writes_result_record_and_clears_pending(self, tmp_path, monkeypatch):
        """Docker execution (even when blocked by unavailable daemon) writes a
        result record and clears the pending proposal."""
        from safecode.sandbox.capabilities import SandboxCapabilityDetector, SandboxCapability
        from safecode.sandbox.docker import DockerDaemonChecker, DockerContainerPlanBuilder
        from safecode.sandbox.adapter import SandboxExecutionRequest
        from safecode.config import SafeCodeConfig
        from safecode.sandbox.execution import SandboxExecutionResultStore

        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = SandboxExecutionGate(tmp_path)

        req = SandboxExecutionRequest(
            command=["echo", "hello"],
            cwd=tmp_path,
            purpose="shell",
            allow_network=False,
            readonly_filesystem=True,
            writable_paths=[],
            env={},
            timeout_seconds=30,
        )
        docker_plan_obj = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(req)
        plan = _make_plan(
            backend=SandboxBackend.DOCKER,
            container_preview=docker_plan_obj.argv,
            container_backend="docker",
        )
        proposal = gate.propose(plan, "shell")
        gate.approve()

        original_detect_all = SandboxCapabilityDetector.detect_all

        def patched_detect_all(self):
            caps = original_detect_all(self)
            return [
                SandboxCapability(
                    backend=SandboxBackend.DOCKER,
                    available=True,
                    supported_platforms=["all"],
                    reason="mocked",
                )
                if cap.backend == SandboxBackend.DOCKER
                else cap
                for cap in caps
            ]

        monkeypatch.setattr(SandboxCapabilityDetector, "detect_all", patched_detect_all)
        monkeypatch.setattr(
            DockerDaemonChecker,
            "check",
            lambda self: (False, "no daemon"),
        )

        result = gate.execute_pending()
        assert result.executed is False
        # Pending is cleared (terminal state)
        assert not gate.pending_path.exists()
        # Result record written
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(proposal.proposal_id)
        assert record is not None
        assert record.backend == "docker"


# ── regression tests ──────────────────────────────────────────────────


class TestExistingSuiteRegression:
    def test_factory_plan_works(self, tmp_path):
        plan = SandboxAdapterFactory(tmp_path).create_plan(["echo", "hello"])
        assert plan.dry_run is True

    def test_mcp_readonly_works(self, tmp_path, monkeypatch):
        from safecode.mcp.runner import MCPReadOnlyRunner
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        sp = tmp_path / "mock_server.py"
        sp.write_text(
            "import json,sys\np=json.loads(sys.stdin.read() or '{}')\nprint(json.dumps({'output':{'ok':True}}))",
            encoding="utf-8",
        )
        (tmp_path / ".sac").mkdir()
        (tmp_path / ".sac" / "mcp.toml").write_text(
            f'[servers.mock]\ncommand = "{shlex.join([sys.executable, str(sp)])}"\nenabled = true\n',
            encoding="utf-8",
        )
        c = SafeCodeConfig()
        c.shell.allowed_commands = [sys.executable]
        c.shell.require_confirm_for_medium = False
        c.sandbox.network_enabled = True
        r = MCPReadOnlyRunner(tmp_path, c).call_readonly("mock", "mock.list", {})
        assert r.blocked is False
