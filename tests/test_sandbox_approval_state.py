"""Sandbox execution approval state tests for v1.7.6.

Verifies user-level approval lifecycle: approve, load, check, revoke.
All operations are dry-run only — no external commands are executed.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from safecode.audit.logger import AuditLogger
from safecode.config import SafeCodeConfig
from safecode.cli import app
from safecode.sandbox.adapter import SandboxBackend, SandboxExecutionPlan
from safecode.sandbox.approvals import (
    SANDBOX_APPROVAL_POLICY_VERSION,
    SandboxExecutionApproval,
    SandboxExecutionApprovalStore,
)
from safecode.sandbox.execution import SandboxExecutionGate
from safecode.sandbox.factory import SandboxAdapterFactory

runner = CliRunner()


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


# ── approval store tests ──────────────────────────────────────────────


class TestApprovalStore:
    def test_approve_writes_outside_project(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        approval = store.approve("proposal-1", "none", "abc123", None)
        assert ad.exists()
        assert store.approval_path_for(approval.proposal_id).exists()

    def test_project_local_dir_rejected(self, tmp_path, monkeypatch):
        local = tmp_path / "approvals"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(local))
        with pytest.raises(PermissionError, match="outside"):
            SandboxExecutionApprovalStore(tmp_path)

    def test_is_approved_true_for_matching(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("proposal-1", "none", "abc123", None)
        assert store.is_approved("proposal-1", "none", "abc123", None) is True

    def test_expired_returns_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        a = store.approve("proposal-1", "none", "abc123", None, ttl_minutes=-1)
        assert store.is_approved("proposal-1", "none", "abc123", None) is False

    def test_malformed_returns_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("proposal-1", "none", "abc123", None)
        path = store.approval_path_for("proposal-1")
        path.write_text("{not valid json", encoding="utf-8")
        assert store.is_approved("proposal-1", "none", "abc123", None) is False

    def test_mismatched_command_hash_returns_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("proposal-1", "none", "abc123", None)
        assert store.is_approved("proposal-1", "none", "different", None) is False

    def test_mismatched_preview_hash_returns_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("proposal-1", "none", "abc123", "prev-hash")
        assert store.is_approved("proposal-1", "none", "abc123", "diff-hash") is False

    def test_mismatched_backend_returns_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("proposal-1", "none", "abc123", None)
        assert store.is_approved("proposal-1", "docker", "abc123", None) is False

    def test_mismatched_project_key_returns_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store_a = SandboxExecutionApprovalStore(tmp_path)
        store_a.approve("proposal-1", "none", "abc123", None)
        other = tmp_path / "other_project"
        other.mkdir(exist_ok=True)
        store_b = SandboxExecutionApprovalStore(other)
        assert store_b.is_approved("proposal-1", "none", "abc123", None) is False

    def test_mismatched_policy_version_returns_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("proposal-1", "none", "abc123", None)
        path = store.approval_path_for("proposal-1")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["policy_version"] = "old-version"
        path.write_text(json.dumps(data), encoding="utf-8")
        assert store.is_approved("proposal-1", "none", "abc123", None) is False

    def test_mismatched_proposal_id_returns_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("proposal-1", "none", "abc123", None)
        path = store.approval_path_for("proposal-1")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["proposal_id"] = "proposal-2"
        path.write_text(json.dumps(data), encoding="utf-8")
        assert store.is_approved("proposal-1", "none", "abc123", None) is False

    def test_proposal_id_cannot_escape_approval_dir(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        path = store.approval_path_for("../../outside")
        assert path.parent == ad
        assert path.name.endswith(".json")
        assert ".." not in path.name
        assert "/" not in path.name

    def test_revoke_removes_approval(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("proposal-1", "none", "abc123", None)
        assert store.revoke("proposal-1") is True
        assert not store.approval_path_for("proposal-1").exists()

    def test_revoke_without_approval_safe(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        assert store.revoke("nonexistent") is False


# ── gate integration tests ────────────────────────────────────────────


class TestGateApprovalIntegration:
    def test_approve_writes_approval(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        approval = gate.approve()
        assert approval is not None
        assert SandboxExecutionApprovalStore(tmp_path).approval_path_for(approval.proposal_id).exists()

    def test_approve_writes_audit(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        assert any(e.type == "sandbox_execution_approved" and e.status == "success" for e in events)

    def test_execute_unapproved_writes_audit(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        assert any(e.type == "sandbox_execution_unapproved_blocked" and e.status == "blocked" for e in events)

    def test_execute_approved_writes_audit(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        assert any(e.type == "sandbox_execution_approved_but_disabled" and e.status == "blocked" for e in events)

    def test_audit_no_env_values(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        plan = _make_plan(env_keys=["SECRET_TOKEN", "SECRET_VALUE"])
        gate.propose(plan, "shell")
        gate.approve()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        for e in events:
            assert "SECRET_VALUE" not in str(e.metadata)

    def test_revoke_works(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        approval = gate.revoke()
        assert approval is not None


# ── CLI tests ──────────────────────────────────────────────────────────


class TestApprovalCli:
    def test_cli_approve_works(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["sandbox", "propose", "git", "status"])
        r = runner.invoke(app, ["sandbox", "approve"])
        assert r.exit_code == 0
        assert "Approved" in r.stdout

    def test_cli_approvals_shows_status(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["sandbox", "propose", "git", "status"])
        runner.invoke(app, ["sandbox", "approve"])
        r = runner.invoke(app, ["sandbox", "approvals"])
        assert "yes" in r.stdout

    def test_cli_revoke_works(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["sandbox", "propose", "git", "status"])
        runner.invoke(app, ["sandbox", "approve"])
        r = runner.invoke(app, ["sandbox", "revoke"])
        assert r.exit_code == 0


# ── regression ────────────────────────────────────────────────────────


class TestExistingSuiteRegression:
    def test_proposal_lifecycle_works(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        assert gate.store.exists()
        gate.discard()
        assert not gate.store.exists()

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
