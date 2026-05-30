"""Sandbox execution security eval suite for v1.8.0.

Systematically verifies the real (Noop-only) sandbox execution path:

A. Execution Gate — Noop adapter executes when all checks pass.
B. Blocked Paths — missing/corrupt proposal, unapproved/expired approval,
   command policy denial, network policy conflict, unsupported backend.
C. Audit Semantics — execution_completed / execution_blocked events.
D. Regression — existing sandbox suites keep passing.

CLI behavior is covered by the existing sandbox CLI suites; this file focuses
on the programmatic execution gate and policy boundaries.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from safecode.audit.logger import AuditLogger
from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import (
    DockerSandboxAdapter,
    LinuxBubblewrapAdapter,
    MacOSSeatbeltAdapter,
    NoopSandboxAdapter,
    SandboxBackend,
    SandboxExecutionPlan,
)
from safecode.sandbox.approvals import SandboxExecutionApprovalStore
from safecode.sandbox.capabilities import SandboxCapability
from safecode.sandbox.execution import SandboxExecutionGate


def _setup_gate(tmp_path, monkeypatch):
    """Create a SandboxExecutionGate with approval + anchor dirs outside project."""
    ad = tmp_path.parent / f"approvals-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
    anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
    return SandboxExecutionGate(tmp_path)


def _make_plan(**kwargs):
    d = {
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
    d.update(kwargs)
    return SandboxExecutionPlan(**d)


# ── A. Execution Gate ───────────────────────────────────────────────────


class TestExecutionGateReal:
    """Noop adapter actually executes commands when all preflight checks pass."""

    def test_noop_supports_execution(self):
        assert NoopSandboxAdapter().supports_execution() is True

    def test_execute_safe_command_success(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is True
        assert result.dry_run is False
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_execute_stdout_captured(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "captured-stdout-test"]), "shell")
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is True
        assert result.exit_code == 0
        assert "captured-stdout-test" in result.stdout

    def test_execute_writes_audit_completed(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        types = [e.type for e in events]
        assert "sandbox_execution_completed" in types


# ── B. Blocked Paths ────────────────────────────────────────────────────


class TestBlockedPaths:
    """Execution is blocked for every reason that preflight detects."""

    def test_no_proposal(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        result = gate.execute_pending()
        assert result.executed is False
        assert "No pending" in result.message

    def test_no_approval(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        result = gate.execute_pending()
        assert result.executed is False
        assert "Approval" in result.message

    def test_expired_approval(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve(ttl_minutes=0)  # immediately expired
        result = gate.execute_pending()
        assert result.executed is False
        assert "Approval" in result.message

    def test_command_policy_denies_dangerous(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["rm", "-rf", "/"]), "shell")
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is False

    def test_command_policy_blocks_curl(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["curl", "https://example.com"]), "shell")
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is False

    def test_backend_not_supported_macos(self, tmp_path, monkeypatch):
        """macOS Seatbelt adapter still returns supports_execution=False."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(
            _make_plan(
                backend=SandboxBackend.MACOS_SEATBELT,
                profile_preview="(deny default)",
                profile_backend="macos_seatbelt",
            ),
            "shell",
        )
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is False

    def test_backend_not_supported_linux_bwrap(self, tmp_path, monkeypatch):
        """Linux Bubblewrap adapter still returns supports_execution=False."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(
            _make_plan(
                backend=SandboxBackend.LINUX_BUBBLEWRAP,
                args_preview=["bwrap", "--ro-bind", "/"],
                args_backend="linux_bubblewrap",
            ),
            "shell",
        )
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is False

    def test_backend_not_supported_docker(self, tmp_path, monkeypatch):
        """Docker adapter still returns supports_execution=False."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(
            _make_plan(
                backend=SandboxBackend.DOCKER,
                container_preview=["docker", "run", "--rm"],
                container_backend="docker",
            ),
            "shell",
        )
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is False

    def test_corrupt_proposal_blocked(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        raw = json.loads(gate.pending_path.read_text(encoding="utf-8"))
        raw["command"] = ["rm", "-rf", "/"]
        gate.pending_path.write_text(json.dumps(raw), encoding="utf-8")
        result = gate.execute_pending()
        assert result.executed is False

    def test_preview_hash_mismatch_profile(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(
            _make_plan(
                backend=SandboxBackend.MACOS_SEATBELT,
                profile_preview="(deny default)",
                profile_backend="macos_seatbelt",
            ),
            "shell",
        )
        gate.approve()
        raw = json.loads(gate.pending_path.read_text(encoding="utf-8"))
        raw["preview_hash"] = "00000000000000000000"
        gate.pending_path.write_text(json.dumps(raw), encoding="utf-8")
        result = gate.execute_pending()
        assert result.executed is False

    def test_network_policy_conflict(self, tmp_path, monkeypatch):
        from safecode.config import SafeCodeConfig

        gate = _setup_gate(tmp_path, monkeypatch)
        cfg = SafeCodeConfig()
        cfg.sandbox.network_enabled = False
        gate.config = cfg
        gate.propose(_make_plan(network_enabled=True), "shell")
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is False

    def test_writable_path_escape(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(
            _make_plan(writable_paths=["/etc/passwd"]),
            "shell",
        )
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is False


# ── C. Audit Semantics ──────────────────────────────────────────────────


class TestAuditSemantics:
    def test_execution_completed_event(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        completed = [e for e in events if e.type == "sandbox_execution_completed"]
        assert len(completed) >= 1
        assert "exit_code=0" in completed[0].message

    def test_execution_blocked_event(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        blocked = [e for e in events if e.type == "sandbox_execution_blocked"]
        assert len(blocked) >= 1
        assert blocked[0].status == "blocked"

    def test_audit_metadata_no_env_values_on_completed(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(env_keys=["SECRET_TOKEN"]), "shell")
        gate.approve()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        completed = [e for e in events if e.type == "sandbox_execution_completed"]
        md = completed[0].metadata
        assert "SECRET_TOKEN" not in str(md)

    def test_audit_metadata_has_proposal_id(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        proposal = gate.propose(_make_plan(), "shell")
        gate.approve()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        completed = [e for e in events if e.type == "sandbox_execution_completed"]
        assert completed[0].metadata["proposal_id"] == proposal.proposal_id

    def test_completed_audit_metadata_has_dry_run_false(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        completed = [e for e in events if e.type == "sandbox_execution_completed"]
        assert completed[0].metadata["dry_run"] == "false"

    def test_blocked_audit_metadata_has_dry_run_true(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        blocked = [e for e in events if e.type == "sandbox_execution_blocked"]
        assert blocked[0].metadata["dry_run"] == "true"

    def test_no_subprocess_on_blocked_path(self, tmp_path, monkeypatch):
        """When preflight blocks, subprocess.run is never called."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        gate.execute_pending()
        assert len(called) == 0


# ── D. Execution Result Semantics ───────────────────────────────────────


class TestExecutionResultSemantics:
    def test_successful_execution_has_dry_run_false(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is True
        assert result.dry_run is False
        assert "Exit code" in result.message or "exit_code" in result.message.lower()

    def test_blocked_execution_has_dry_run_true(self, tmp_path, monkeypatch):
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        result = gate.execute_pending()
        assert result.executed is False
        assert result.dry_run is True

    def test_roundtrip_propose_approve_execute(self, tmp_path, monkeypatch):
        """Full programmatic roundtrip: propose → approve → execute."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "roundtrip-ok"]), "shell")
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is True
        assert "roundtrip-ok" in result.stdout


# ── E. Regression ───────────────────────────────────────────────────────


class TestRegression:
    def test_other_adapters_still_dry_run(self):
        noop_cap = SandboxCapability(
            backend=SandboxBackend.NONE,
            available=True,
            supported_platforms=["darwin", "linux"],
            reason="Noop always available.",
        )
        mac_cap = SandboxCapability(
            backend=SandboxBackend.MACOS_SEATBELT,
            available=True,
            supported_platforms=["darwin"],
            reason="macOS sandbox-exec available.",
        )
        linux_cap = SandboxCapability(
            backend=SandboxBackend.LINUX_BUBBLEWRAP,
            available=True,
            supported_platforms=["linux"],
            reason="bwrap available.",
        )
        docker_cap = SandboxCapability(
            backend=SandboxBackend.DOCKER,
            available=True,
            supported_platforms=["darwin", "linux"],
            reason="Docker daemon available.",
        )

        assert MacOSSeatbeltAdapter(mac_cap).supports_execution() is False
        assert LinuxBubblewrapAdapter(linux_cap).supports_execution() is False
        assert DockerSandboxAdapter(docker_cap).supports_execution() is False
        assert NoopSandboxAdapter().supports_execution() is True

    def test_factory_plan_still_works(self, tmp_path):
        from safecode.sandbox.factory import SandboxAdapterFactory
        plan = SandboxAdapterFactory(tmp_path).create_plan(["echo", "hello"])
        assert plan.dry_run is True

    def test_mcp_readonly_still_works(self, tmp_path, monkeypatch):
        from safecode.mcp.runner import MCPReadOnlyRunner
        from safecode.config import SafeCodeConfig

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

    def test_approval_store_still_works(self, tmp_path, monkeypatch):
        from safecode.sandbox.approvals import (
            SANDBOX_APPROVAL_POLICY_VERSION,
            SandboxExecutionApprovalStore,
        )
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        assert store.is_approved("p1", "none", "abc", None) is True
        assert store.is_approved("p1", "none", "wrong", None) is False
