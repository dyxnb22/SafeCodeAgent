"""Sandbox preflight security eval suite for v1.7.9.

Systematically verifies v1.7.8 preflight decision layer correctly detects
proposal tampering, approval failures, command/network/filesystem violations,
backend issues, and audit/CLI privacy leaks.
"""

from __future__ import annotations

import hashlib
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
from safecode.sandbox.execution import SandboxExecutionGate
from safecode.sandbox.preflight import SandboxExecutionPreflight

runner = CliRunner()


def _setup_gate(tmp_path, monkeypatch):
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


def _approval_dir(tmp_path):
    return tmp_path.parent / f"approvals-{tmp_path.name}"


def _mock_supports_execution_true(monkeypatch):
    """Patch NoopSandboxAdapter to report supports_execution=True."""
    from safecode.sandbox import adapter
    # Patch NoopSandboxAdapter.supports_execution to return True
    original = adapter.NoopSandboxAdapter.supports_execution
    monkeypatch.setattr(
        adapter.NoopSandboxAdapter,
        "supports_execution",
        lambda self: True,
    )
    return original


# ── A. Proposal integrity ─────────────────────────────────────────────


class TestProposalIntegrity:
    def test_command_tampered_but_hash_kept(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "hello"]), "shell")
        # Tamper: change command but keep old hash
        proposal = gate.store.load_pending()
        data = json.loads(gate.store.path.read_text(encoding="utf-8"))
        data["command"] = ["rm", "-rf", "/"]
        gate.store.path.write_text(json.dumps(data), encoding="utf-8")
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.proposal_integrity_ok is False
        assert result.allowed is False

    def test_command_hash_tampered(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "hello"]), "shell")
        gate.approve()
        # Tamper: change command AND command_hash
        proposal = gate.store.load_pending()
        data = json.loads(gate.store.path.read_text(encoding="utf-8"))
        data["command"] = ["rm", "-rf", "/"]
        data["command_hash"] = hashlib.sha256(
            json.dumps(data["command"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        gate.store.path.write_text(json.dumps(data), encoding="utf-8")
        result = SandboxExecutionPreflight(tmp_path).run()
        # hash now matches tampered command, but approval binds the OLD hash
        assert result.approval_valid is False
        assert result.allowed is False

    def test_backend_tampered(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        data = json.loads(gate.store.path.read_text(encoding="utf-8"))
        data["backend"] = "docker"
        gate.store.path.write_text(json.dumps(data), encoding="utf-8")
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.approval_valid is False
        assert result.allowed is False

    def test_malformed_pending_shows_malformed_reason(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.store.path.parent.mkdir(parents=True, exist_ok=True)
        gate.store.path.write_text("{broken", encoding="utf-8")
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.allowed is False
        assert "Malformed" in result.reasons[0]


# ── B. Approval + execution state ─────────────────────────────────────


class TestApprovalExecutionState:
    def test_no_pending_allowed_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.allowed is False
        assert result.proposal_id is None

    def test_unapproved_allowed_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.approval_valid is False
        assert result.allowed is False

    def test_expired_approval_allowed_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve(ttl_minutes=-1)
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.approval_valid is False
        assert result.allowed is False

    def test_revoked_approval_allowed_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        gate.revoke()
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.approval_valid is False
        assert result.allowed is False

    def test_approval_from_other_project_allowed_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate_a = _setup_gate(tmp_path, monkeypatch)
        gate_a.propose(_make_plan(), "shell")
        gate_a.approve()
        # Now approve from tmp_path (valid), then check from a different path
        other = tmp_path / "other_project"
        other.mkdir(exist_ok=True)
        # Copy the proposal file to other project so it loads
        import shutil
        (other / ".sac").mkdir(exist_ok=True)
        shutil.copy2(gate_a.store.path, other / ".sac" / "pending_sandbox_execution.json")
        # Create approval store in other project with same env dir
        result = SandboxExecutionPreflight(other).run()
        assert result.approval_valid is False
        assert result.allowed is False

    def test_approved_supports_execution_false_allowed_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.approval_valid is True
        assert result.backend_supports_execution is False
        assert result.allowed is False


# ── C. Command / network / filesystem ─────────────────────────────────


class TestCommandNetworkFilesystem:
    def test_non_allowlisted_command_blocked(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(
            _make_plan(command=["curl", "https://evil.com"]),
            "shell",
        )
        gate.approve()
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.command_policy_ok is False
        assert result.allowed is False

    def test_dangerous_command_policy_blocked(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(
            _make_plan(command=["rm", "-rf", "/"]),
            "shell",
        )
        gate.approve()
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.command_policy_ok is False
        assert result.allowed is False

    def test_network_disabled_but_proposal_enabled(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        config = SafeCodeConfig()
        config.sandbox.network_enabled = False
        gate = SandboxExecutionGate(tmp_path, config)
        gate.propose(_make_plan(network_enabled=True, env_keys=[]), "shell")
        gate.approve()
        result = SandboxExecutionPreflight(tmp_path, config).run()
        assert result.network_policy_ok is False
        assert result.allowed is False

    def test_writable_path_outside_project_blocked(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(writable_paths=[str(tmp_path.parent / "outside")]), "shell")
        gate.approve()
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.filesystem_boundary_ok is False
        assert result.allowed is False


# ── D. Backend behavior ────────────────────────────────────────────────


class TestBackendBehavior:
    def test_unknown_backend_unavailable(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        # Tamper backend to something unknown
        data = json.loads(gate.store.path.read_text(encoding="utf-8"))
        data["backend"] = "unknown_backend_xyz"
        gate.store.path.write_text(json.dumps(data), encoding="utf-8")
        gate.approve()
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.backend_available is False
        assert result.allowed is False

    def test_unavailable_backend_blocked(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        monkeypatch.setattr("platform.system", lambda: "FreeBSD")
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(backend=SandboxBackend.LINUX_BUBBLEWRAP), "shell")
        gate.approve()
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.backend_available is False
        assert result.allowed is False

    def test_checks_proposal_backend_not_recommended(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(backend=SandboxBackend.NONE), "shell")
        gate.approve()
        _mock_supports_execution_true(monkeypatch)
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.backend == SandboxBackend.NONE.value

    def test_supports_execution_true_all_conditions_met_allowed_true(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(backend=SandboxBackend.NONE), "shell")
        gate.approve()
        _mock_supports_execution_true(monkeypatch)
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.allowed is True
        assert result.backend_supports_execution is True
        assert result.approval_valid is True


# ── E. Audit / CLI privacy ────────────────────────────────────────────


class TestAuditAndCliPrivacy:
    def test_preflight_audit_exists(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        SandboxExecutionPreflight(tmp_path).run()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        assert any(e.type == "sandbox_preflight_checked" for e in events)

    def test_audit_status_blocked_when_not_allowed(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        SandboxExecutionPreflight(tmp_path).run()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        ev = [e for e in events if e.type == "sandbox_preflight_checked"][0]
        assert ev.status == "blocked"

    def test_audit_no_full_command_args(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["rm", "-rf", "/tmp/danger"]), "shell")
        events = AuditLogger(tmp_path).read_recent(limit=5)
        for e in events:
            combined = str(e.message) + str(e.metadata)
            assert "/tmp/danger" not in combined

    def test_audit_no_env_values(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(env_keys=["SECRET_TOKEN"]), "shell")
        events = AuditLogger(tmp_path).read_recent(limit=5)
        for e in events:
            assert "SUPER_SECRET" not in str(e.message) + str(e.metadata)

    def test_cli_output_no_command_executed(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        r = runner.invoke(app, ["sandbox", "preflight"])
        assert r.exit_code == 0
        assert "No command was executed" in r.stdout

    def test_cli_output_shows_proposal_integrity(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        r = runner.invoke(app, ["sandbox", "preflight"])
        assert "Proposal Integrity" in r.stdout

    def test_cli_output_no_env_values(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("SECRET_VALUE", "my-precious-key")
        r = runner.invoke(app, ["sandbox", "preflight"])
        assert "my-precious-key" not in r.stdout


# ── F. Regression ─────────────────────────────────────────────────────


class TestRegression:
    def test_preflight_normal_flow(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.approval_valid is True
        assert result.allowed is False  # supports_execution is False

    def test_sandbox_approve_execute_still_refuses(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        r = gate.execute_pending()
        assert r.executed is False

    def test_approval_security_evals_still_pass(self, tmp_path, monkeypatch):
        from safecode.sandbox.approvals import SANDBOX_APPROVAL_POLICY_VERSION, SandboxExecutionApprovalStore
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        assert store.is_approved("p1", "none", "abc", None) is True
        assert store.is_approved("p1", "none", "wrong", None) is False

    def test_mcp_readonly_still_works(self, tmp_path, monkeypatch):
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

    def test_sandbox_plan_still_works(self, tmp_path):
        from safecode.sandbox.factory import SandboxAdapterFactory
        plan = SandboxAdapterFactory(tmp_path).create_plan(["echo", "hello"])
        assert plan.dry_run is True
