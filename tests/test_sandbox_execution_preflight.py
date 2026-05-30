"""Sandbox execution preflight tests for v1.7.8.

Verifies the unified preflight check layer correctly evaluates all
conditions without executing any external commands.
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
from safecode.sandbox.adapter import SandboxBackend, SandboxExecutionPlan
from safecode.sandbox.execution import SandboxExecutionGate
from safecode.sandbox.preflight import SandboxExecutionPreflight


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


# ── A. No proposal ────────────────────────────────────────────────────


class TestNoProposal:
    def test_no_pending_proposal_allowed_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.allowed is False
        assert result.proposal_id is None
        assert "No pending" in result.reasons[0]


# ── B. Unapproved / expired / mismatched ──────────────────────────────


class TestApprovalChecks:
    def test_unapproved_proposal_approval_valid_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.approval_valid is False
        assert result.allowed is False

    def test_approved_but_adapter_supports_execution_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        # v1.8.0: macOS backend still returns supports_execution=False
        gate.propose(
            _make_plan(
                backend=SandboxBackend.MACOS_SEATBELT,
                profile_preview="(deny default)",
                profile_backend="macos_seatbelt",
            ),
            "shell",
        )
        gate.approve()
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.approval_valid is True
        assert result.backend_supports_execution is False
        assert result.allowed is False

    def test_expired_approval(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve(ttl_minutes=-1)
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.approval_valid is False

    def test_command_hash_mismatch_approval(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "v1"]), "shell")
        p = gate.store.load_pending()
        from safecode.sandbox.approvals import SandboxExecutionApprovalStore
        astore = SandboxExecutionApprovalStore(tmp_path)
        astore.approve(p.proposal_id, p.backend, "different-hash", p.preview_hash)
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.approval_valid is False

    def test_backend_mismatch_approval(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        p = gate.store.load_pending()
        from safecode.sandbox.approvals import SandboxExecutionApprovalStore
        astore = SandboxExecutionApprovalStore(tmp_path)
        astore.approve(p.proposal_id, "docker", p.command_hash, p.preview_hash)
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.approval_valid is False


# ── C. Network / filesystem ───────────────────────────────────────────


class TestNetworkAndFilesystem:
    def test_network_disabled_but_proposal_enabled(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        config = SafeCodeConfig()
        config.sandbox.network_enabled = False
        gate = SandboxExecutionGate(tmp_path, config)
        gate.propose(
            _make_plan(network_enabled=True, env_keys=[]),
            "shell",
        )
        gate.approve()
        result = SandboxExecutionPreflight(tmp_path, config).run()
        assert result.network_policy_ok is False
        assert result.allowed is False

    def test_writable_path_outside_project(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        outside = str(tmp_path.parent / "outside")
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(
            _make_plan(writable_paths=[outside]),
            "shell",
        )
        gate.approve()
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.filesystem_boundary_ok is False
        assert result.allowed is False


# ── D. Malformed / audit / subprocess ─────────────────────────────────


class TestEdgeCases:
    def test_malformed_pending_allowed_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.store.path.parent.mkdir(parents=True, exist_ok=True)
        gate.store.path.write_text("{broken", encoding="utf-8")
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.allowed is False
        assert "Malformed" in result.reasons[0]

    def test_tampered_proposal_command_hash_blocked(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "hello"]), "shell")
        gate.approve()
        data = json.loads(gate.store.path.read_text(encoding="utf-8"))
        data["command"] = ["pwd"]
        gate.store.path.write_text(json.dumps(data), encoding="utf-8")
        result = SandboxExecutionPreflight(tmp_path).run()
        assert result.proposal_integrity_ok is False
        assert result.allowed is False

    def test_preflight_no_subprocess(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: called.append(1))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        SandboxExecutionPreflight(tmp_path).run()
        assert len(called) == 0

    def test_audit_event_written(self, tmp_path, monkeypatch):
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

    def test_audit_no_env_values(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(env_keys=["SECRET_TOKEN"]), "shell")
        gate.approve()
        SandboxExecutionPreflight(tmp_path).run()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        for e in events:
            combined = str(e.message) + str(e.metadata)
            assert "SUPER_SECRET" not in combined


# ── E. CLI ────────────────────────────────────────────────────────────


class TestPreflightCli:
    def test_cli_preflight_no_command_executed(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from safecode.cli import app
        runner = CliRunner()
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        r = runner.invoke(app, ["sandbox", "preflight"])
        assert r.exit_code == 0
        assert "No command was executed" in r.stdout


# ── F. Regression ─────────────────────────────────────────────────────


class TestRegression:
    def test_sandbox_propose_still_works(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        assert gate.store.exists()

    def test_sandbox_approve_execute_still_works(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = _setup_gate(tmp_path, monkeypatch)
        # v1.8.0: macOS backend still blocks execution (supports_execution=False)
        gate.propose(
            _make_plan(
                backend=SandboxBackend.MACOS_SEATBELT,
                profile_preview="(deny default)",
                profile_backend="macos_seatbelt",
            ),
            "shell",
        )
        a = gate.approve()
        assert a is not None
        r = gate.execute_pending()
        assert r.executed is False

    def test_mcp_readonly(self, tmp_path, monkeypatch):
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
