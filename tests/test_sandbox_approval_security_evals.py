"""Sandbox approval security eval suite for v1.7.7.

Systematically verifies that the sandbox proposal + approval system resists:
project forgery, path traversal, hash tampering, expiry bypass, env leak,
and audit semantic errors. All operations are dry-run only.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.audit.logger import AuditLogger
from safecode.config import SafeCodeConfig
from safecode.cli import app
from safecode.sandbox.adapter import SandboxBackend, SandboxExecutionPlan
from safecode.sandbox.approvals import (
    SANDBOX_APPROVAL_POLICY_VERSION,
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


# ── A. Approval storage trust boundary ────────────────────────────────


class TestApprovalStorageTrust:
    def test_env_dir_inside_project_rejected(self, tmp_path, monkeypatch):
        local = tmp_path / "approvals"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(local))
        with pytest.raises(PermissionError, match="outside"):
            SandboxExecutionApprovalStore(tmp_path)

    def test_env_dir_subdirectory_of_project_rejected(self, tmp_path, monkeypatch):
        deep = tmp_path / "sub" / "approvals"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(deep))
        with pytest.raises(PermissionError, match="outside"):
            SandboxExecutionApprovalStore(tmp_path)

    def test_default_dir_outside_project(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAFECODE_SANDBOX_APPROVAL_DIR", raising=False)
        store = SandboxExecutionApprovalStore(tmp_path)
        assert str(tmp_path) not in str(store._approval_root)

    def test_project_local_file_not_auto_approved(self, tmp_path, monkeypatch):
        local_approval_root = tmp_path / ".sac" / "sandbox_approvals"
        local_approval_root.mkdir(parents=True)
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        now = datetime.now(timezone.utc)
        payload = {
            "proposal_id": "proposal-1",
            "approved_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=30)).isoformat(),
            "project_root": str(tmp_path.resolve()),
            "project_key": hashlib.sha256(tmp_path.resolve().as_posix().encode("utf-8")).hexdigest(),
            "backend": "none",
            "command_hash": "abc123",
            "preview_hash": None,
            "approved_by": "attacker",
            "policy_version": SANDBOX_APPROVAL_POLICY_VERSION,
        }
        local_path = local_approval_root / store.approval_path_for("proposal-1").name
        local_path.write_text(json.dumps(payload), encoding="utf-8")
        assert store.is_approved("proposal-1", "none", "abc123", None) is False

    def test_approval_path_for_sanitizes_traversal(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        p = store.approval_path_for("../outside")
        assert str(tmp_path) not in str(p)
        assert ".." not in p.name

    def test_approval_path_for_sanitizes_slashes(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        p = store.approval_path_for("a/b/c")
        assert "/" not in p.name

    def test_approval_path_for_sanitizes_absolute_path(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        p = store.approval_path_for("/etc/passwd")
        assert str(p.parent) == str(ad)


# ── B. Approval binding integrity ─────────────────────────────────────


class TestApprovalBindingIntegrity:
    def test_proposal_id_mismatch(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("proposal-1", "none", "abc", None)
        assert store.is_approved("proposal-2", "none", "abc", None) is False

    def test_backend_mismatch(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        assert store.is_approved("p1", "docker", "abc", None) is False

    def test_command_hash_mismatch(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        assert store.is_approved("p1", "none", "xyz", None) is False

    def test_preview_hash_mismatch(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", "prev-a")
        assert store.is_approved("p1", "none", "abc", "prev-b") is False

    def test_project_key_mismatch(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store_a = SandboxExecutionApprovalStore(tmp_path)
        store_a.approve("p1", "none", "abc", None)
        other = tmp_path / "other_project"
        other.mkdir(exist_ok=True)
        store_b = SandboxExecutionApprovalStore(other)
        assert store_b.is_approved("p1", "none", "abc", None) is False

    def test_policy_version_mismatch(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        p = store.approval_path_for("p1")
        data = json.loads(p.read_text(encoding="utf-8"))
        data["policy_version"] = "v0.0.0-old"
        p.write_text(json.dumps(data), encoding="utf-8")
        assert store.is_approved("p1", "none", "abc", None) is False

    def test_expired_ttl(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None, ttl_minutes=-1)
        assert store.is_approved("p1", "none", "abc", None) is False

    def test_invalid_expires_at(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        p = store.approval_path_for("p1")
        data = json.loads(p.read_text(encoding="utf-8"))
        data["expires_at"] = "not-a-date"
        p.write_text(json.dumps(data), encoding="utf-8")
        assert store.is_approved("p1", "none", "abc", None) is False

    def test_malformed_json(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        store.approval_path_for("p1").write_text("{not json", encoding="utf-8")
        assert store.is_approved("p1", "none", "abc", None) is False

    def test_missing_required_field(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        p = store.approval_path_for("p1")
        data = json.loads(p.read_text(encoding="utf-8"))
        del data["command_hash"]
        p.write_text(json.dumps(data), encoding="utf-8")
        assert store.is_approved("p1", "none", "abc", None) is False


# ── C. Execution gate behavior ────────────────────────────────────────


class TestExecutionGateBehavior:
    def test_no_pending_proposal_execute_false(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = SandboxExecutionGate(tmp_path)
        result = gate.execute_pending()
        assert result.executed is False

    def test_unapproved_execute_false_and_audit(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        result = gate.execute_pending()
        assert result.executed is False
        events = AuditLogger(tmp_path).read_recent(limit=5)
        # v1.8.0: unified "sandbox_execution_blocked" for all preflight blocks
        assert any(e.type == "sandbox_execution_blocked" for e in events)

    def test_approved_execute_still_false_unsupported_backend(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        # v1.8.0: use macOS backend which still returns supports_execution=False
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
        events = AuditLogger(tmp_path).read_recent(limit=5)
        assert any(e.type == "sandbox_execution_blocked" for e in events)

    def test_approve_no_subprocess(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        gate.approve()
        assert len(called) == 0

    def test_revoke_no_subprocess(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        gate.revoke()
        assert len(called) == 0

    def test_execute_no_subprocess_unsupported_backend(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = SandboxExecutionGate(tmp_path)
        # v1.8.0: macOS backend still blocks, so subprocess never called
        gate.propose(
            _make_plan(
                backend=SandboxBackend.MACOS_SEATBELT,
                profile_preview="(deny default)",
                profile_backend="macos_seatbelt",
            ),
            "shell",
        )
        gate.approve()
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        gate.execute_pending()
        assert len(called) == 0

    def test_revoke_then_execute_unapproved(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        gate.revoke()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        # v1.8.0: unified "sandbox_execution_blocked" for all preflight blocks
        assert any(e.type == "sandbox_execution_blocked" for e in events)

    def test_duplicate_proposal_still_blocked(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        with pytest.raises(FileExistsError, match="already exists"):
            gate.propose(_make_plan(), "shell")

    def test_corrupt_proposal_still_blocked(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = SandboxExecutionGate(tmp_path)
        gate.store.path.parent.mkdir(parents=True, exist_ok=True)
        gate.store.path.write_text("{broken", encoding="utf-8")
        with pytest.raises(FileExistsError, match="corrupt"):
            gate.propose(_make_plan(), "shell")


# ── D. CLI behavior ───────────────────────────────────────────────────


class TestCLIBehavior:
    def test_approve_no_pending_safe(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["sandbox", "approve"])
        assert result.exit_code == 0
        assert "No pending" in result.stdout

    def test_approvals_expired_shows_no(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["sandbox", "propose", "pwd"])
        gate = SandboxExecutionGate(tmp_path)
        proposal = gate.load_pending()
        assert proposal is not None
        SandboxExecutionApprovalStore(tmp_path).approve(
            proposal.proposal_id,
            proposal.backend,
            proposal.command_hash,
            proposal.preview_hash,
            ttl_minutes=-1,
        )
        result = runner.invoke(app, ["sandbox", "approvals"])
        assert "no" in result.stdout

    def test_execute_never_real(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["sandbox", "propose", "pwd"])
        runner.invoke(app, ["sandbox", "approve"])
        result = runner.invoke(app, ["sandbox", "execute"])
        assert "no" in result.stdout.lower()

    def test_cli_output_no_env_values(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("SECRET_TOKEN", "secret-value-123")
        r1 = runner.invoke(app, ["sandbox", "propose", "pwd"])
        r2 = runner.invoke(app, ["sandbox", "approve"])
        r3 = runner.invoke(app, ["sandbox", "execute"])
        combined = r1.stdout + r2.stdout + r3.stdout
        assert "secret-value-123" not in combined


# ── E. Audit semantics ────────────────────────────────────────────────


class TestAuditSemantics:
    def test_approved_status_is_success(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        approved = [e for e in events if e.type == "sandbox_execution_approved"]
        assert len(approved) >= 1
        assert approved[0].status == "success"

    def test_revoked_status_is_success(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        gate.revoke()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        revoked = [e for e in events if e.type == "sandbox_execution_approval_revoked"]
        assert revoked[0].status == "success"

    def test_unapproved_blocked_status_is_blocked(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        # v1.8.0: unified "sandbox_execution_blocked" for all preflight blocks
        ev = [e for e in events if e.type == "sandbox_execution_blocked"][0]
        assert ev.status == "blocked"

    def test_approved_but_disabled_status_is_blocked_unsupported_backend(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        # v1.8.0: use macOS backend which still blocks execution
        gate.propose(
            _make_plan(
                backend=SandboxBackend.MACOS_SEATBELT,
                profile_preview="(deny default)",
                profile_backend="macos_seatbelt",
            ),
            "shell",
        )
        gate.approve()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        ev = [e for e in events if e.type == "sandbox_execution_blocked"][0]
        assert ev.status == "blocked"

    def test_audit_no_env_values(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        monkeypatch.setenv("SECRET_TOKEN", "secret-value-123")
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(env_keys=["SECRET_TOKEN"]), "shell")
        gate.approve()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=10)
        for e in events:
            combined = str(e.message) + str(e.metadata)
            assert "secret-value-123" not in combined

    def test_audit_no_full_command_args(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(command=["rm", "-rf", "/tmp/danger"]), "shell")
        events = AuditLogger(tmp_path).read_recent(limit=5)
        for e in events:
            combined = str(e.message) + str(e.metadata)
            assert "/tmp/danger" not in combined


# ── F. Regression ─────────────────────────────────────────────────────


class TestRegression:
    def test_proposal_lifecycle(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        assert gate.store.exists()
        gate.discard()
        assert not gate.store.exists()

    def test_approval_lifecycle(self, tmp_path, monkeypatch):
        ad = _approval_dir(tmp_path)
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(_make_plan(), "shell")
        a = gate.approve()
        assert a is not None
        assert gate.load_approval() is not None
        gate.revoke()
        assert gate.load_approval() is None

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

    def test_sandbox_plan(self, tmp_path):
        plan = SandboxAdapterFactory(tmp_path).create_plan(["echo", "hello"])
        assert plan.dry_run is True
