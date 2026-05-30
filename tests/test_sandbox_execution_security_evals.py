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
from safecode.sandbox.execution import (
    SandboxExecutionGate,
    SandboxExecutionResultStore,
)


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


# ── D+. Single-Use Approval (v1.8.1) ──────────────────────────────────────


class TestSingleUseApproval:
    """v1.8.1: approval is consumed after first successful execution."""

    def test_second_execution_blocked_after_first(self, tmp_path, monkeypatch):
        """Execute once successfully, then second attempt is blocked.

        v1.8.3: successful execution clears the pending proposal, so the
        second call reports "No pending" instead of "Approval".
        """
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        r1 = gate.execute_pending()
        assert r1.executed is True
        # Second execution blocked — no pending proposal remains
        r2 = gate.execute_pending()
        assert r2.executed is False
        assert "No pending" in r2.message

    def test_blocked_preflight_does_not_consume(self, tmp_path, monkeypatch):
        """Blocked execution (unsupported backend) does NOT consume approval."""
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
        r1 = gate.execute_pending()
        assert r1.executed is False
        # Approval still valid — not consumed by blocked preflight
        approval_store = SandboxExecutionApprovalStore(tmp_path)
        proposal = gate.load_pending()
        assert approval_store.is_approved(
            proposal.proposal_id,
            proposal.backend,
            proposal.command_hash,
            proposal.preview_hash,
        ) is True

    def test_consumption_audit_event(self, tmp_path, monkeypatch):
        """Successful execution writes sandbox_execution_approval_claimed."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        claimed = [e for e in events if e.type == "sandbox_execution_approval_claimed"]
        assert len(claimed) >= 1
        assert claimed[0].status == "success"

    def test_consumed_approval_fails_is_approved(self, tmp_path, monkeypatch):
        """After consumption, is_approved() returns False for same approval.

        v1.8.3: pending proposal is cleared after execution, so store the
        proposal fields before calling execute_pending().
        """
        gate = _setup_gate(tmp_path, monkeypatch)
        proposal = gate.propose(_make_plan(), "shell")
        gate.approve()
        gate.execute_pending()
        approval_store = SandboxExecutionApprovalStore(tmp_path)
        assert approval_store.is_approved(
            proposal.proposal_id,
            proposal.backend,
            proposal.command_hash,
            proposal.preview_hash,
        ) is False

    def test_legacy_approval_without_consumed_field(self, tmp_path, monkeypatch):
        """Approval file lacking 'consumed' field treated as not-consumed."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        # Strip 'consumed' field to simulate pre-v1.8.1 approval file
        approval_store = SandboxExecutionApprovalStore(tmp_path)
        p = approval_store.approval_path_for(gate.load_pending().proposal_id)
        data = json.loads(p.read_text(encoding="utf-8"))
        del data["consumed"]
        p.write_text(json.dumps(data), encoding="utf-8")
        # Still seen as approved (backward compat)
        proposal = gate.load_pending()
        assert approval_store.is_approved(
            proposal.proposal_id, proposal.backend,
            proposal.command_hash, proposal.preview_hash,
        ) is True

    def test_no_env_value_in_claimed_audit(self, tmp_path, monkeypatch):
        """Claim audit must not leak env values."""
        gate = _setup_gate(tmp_path, monkeypatch)
        monkeypatch.setenv("SECRET_TOKEN", "secret-value-123")
        gate.propose(_make_plan(env_keys=["SECRET_TOKEN"]), "shell")
        gate.approve()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        for e in events:
            combined = str(e.message) + str(e.metadata)
            assert "secret-value-123" not in combined

    def test_unsupported_backend_no_claimed_audit(self, tmp_path, monkeypatch):
        """macOS backend blocked by preflight — no claim audit event written."""
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
        r = gate.execute_pending()
        assert r.executed is False
        events = AuditLogger(tmp_path).read_recent(limit=5)
        claimed = [e for e in events if e.type == "sandbox_execution_approval_claimed"]
        assert len(claimed) == 0


# ── D++. Atomic Approval Claim (v1.8.2) ───────────────────────────────────


class TestAtomicApprovalClaim:
    """v1.8.2: approval is atomically claimed before execution to close
    the TOCTOU window between preflight and ShellRunner.run()."""

    def test_concurrent_claim_only_one_succeeds(self, tmp_path, monkeypatch):
        """Two claim_for_execution calls on the same approval: only one wins."""
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        assert store.is_approved("p1", "none", "abc", None) is True
        c1 = store.claim_for_execution("p1", "none", "abc", None)
        c2 = store.claim_for_execution("p1", "none", "abc", None)
        assert c1 is True
        assert c2 is False

    def test_claim_fails_after_successful_execution(self, tmp_path, monkeypatch):
        """After a full execute_pending cycle, claim on same approval fails.

        v1.8.3: pending proposal is cleared after execution, so store the
        proposal fields before calling execute_pending().
        """
        gate = _setup_gate(tmp_path, monkeypatch)
        proposal = gate.propose(_make_plan(), "shell")
        gate.approve()
        r1 = gate.execute_pending()
        assert r1.executed is True
        # Direct claim on the same approval must fail
        approval_store = SandboxExecutionApprovalStore(tmp_path)
        c2 = approval_store.claim_for_execution(
            proposal.proposal_id,
            proposal.backend,
            proposal.command_hash,
            proposal.preview_hash,
        )
        assert c2 is False

    def test_claim_failure_does_not_call_shell_runner(self, tmp_path, monkeypatch):
        """When claim_for_execution returns False, subprocess.run is never called."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        # Pre-consume the approval so claim_for_execution inside execute_pending fails
        approval_store = SandboxExecutionApprovalStore(tmp_path)
        proposal = gate.load_pending()
        approval_store.consume(proposal.proposal_id)
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        result = gate.execute_pending()
        assert result.executed is False
        assert len(called) == 0

    def test_blocked_preflight_does_not_call_claim(self, tmp_path, monkeypatch):
        """Blocked preflight returns before claim_for_execution is reached."""
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
        r = gate.execute_pending()
        assert r.executed is False
        # Approval should still be unclaimed (not consumed)
        approval_store = SandboxExecutionApprovalStore(tmp_path)
        proposal = gate.load_pending()
        assert approval_store.is_approved(
            proposal.proposal_id,
            proposal.backend,
            proposal.command_hash,
            proposal.preview_hash,
        ) is True

    def test_non_zero_exit_still_consumed(self, tmp_path, monkeypatch):
        """Even when the command exits non-zero, the approval is consumed."""
        from safecode.config import SafeCodeConfig

        gate = _setup_gate(tmp_path, monkeypatch)
        cfg = SafeCodeConfig()
        cfg.shell.allowed_commands = [sys.executable]
        cfg.shell.require_confirm_for_medium = False
        gate.config = cfg
        # python running a non-existent script exits non-zero
        gate.propose(
            _make_plan(command=[sys.executable, "/tmp/nonexistent_script.py"]),
            "shell",
        )
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is True
        assert result.exit_code != 0
        # Approval is consumed — second execution blocked
        r2 = gate.execute_pending()
        assert r2.executed is False

    def test_legacy_approval_without_consumed_claimable(self, tmp_path, monkeypatch):
        """Approval file lacking 'consumed' field can be claimed exactly once."""
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        # Strip 'consumed' field
        p = store.approval_path_for("p1")
        data = json.loads(p.read_text(encoding="utf-8"))
        del data["consumed"]
        p.write_text(json.dumps(data), encoding="utf-8")
        # First claim succeeds
        assert store.claim_for_execution("p1", "none", "abc", None) is True
        # Second claim fails
        assert store.claim_for_execution("p1", "none", "abc", None) is False

    def test_malformed_approval_claim_fails(self, tmp_path, monkeypatch):
        """Corrupt approval JSON causes claim to fail closed."""
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        p = store.approval_path_for("p1")
        p.write_text("not valid json", encoding="utf-8")
        assert store.claim_for_execution("p1", "none", "abc", None) is False

    def test_expired_approval_claim_fails(self, tmp_path, monkeypatch):
        """Expired approval cannot be claimed."""
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None, ttl_minutes=0)
        assert store.claim_for_execution("p1", "none", "abc", None) is False

    def test_mismatched_backend_claim_fails(self, tmp_path, monkeypatch):
        """Claim with wrong backend fails closed."""
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        assert store.claim_for_execution("p1", "docker", "abc", None) is False

    def test_mismatched_command_hash_claim_fails(self, tmp_path, monkeypatch):
        """Claim with wrong command_hash fails closed."""
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        store = SandboxExecutionApprovalStore(tmp_path)
        store.approve("p1", "none", "abc", None)
        assert store.claim_for_execution("p1", "none", "wrong", None) is False

    def test_claim_audit_event_written(self, tmp_path, monkeypatch):
        """Successful claim writes sandbox_execution_approval_claimed audit event."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        claimed = [e for e in events if e.type == "sandbox_execution_approval_claimed"]
        assert len(claimed) >= 1
        assert claimed[0].status == "success"
        assert "claimed" in claimed[0].message.lower()

    def test_no_env_leak_in_claimed_audit(self, tmp_path, monkeypatch):
        """Claim audit event must not leak env values or full command."""
        gate = _setup_gate(tmp_path, monkeypatch)
        monkeypatch.setenv("SECRET_TOKEN", "secret-value-123")
        gate.propose(_make_plan(env_keys=["SECRET_TOKEN"]), "shell")
        gate.approve()
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        for e in events:
            combined = str(e.message) + str(e.metadata)
            assert "secret-value-123" not in combined

    def test_claim_failure_audit_is_blocked(self, tmp_path, monkeypatch):
        """When claim fails inside execute_pending, audit event has status=blocked."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        # Force claim_for_execution to fail while approval is still valid
        monkeypatch.setattr(
            SandboxExecutionApprovalStore,
            "claim_for_execution",
            lambda *a, **kw: False,
        )
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=5)
        blocked = [e for e in events if e.type == "sandbox_execution_blocked"]
        claim_blocked = [e for e in blocked if "claim" in e.message.lower()]
        assert len(claim_blocked) >= 1


# ── D+++. Execution Result Lifecycle (v1.8.3) ────────────────────────────


class TestExecutionResultLifecycle:
    """v1.8.3: execution result records are persisted with redacted/truncated
    output; pending proposal is cleared on execution or claim failure."""

    def test_successful_execution_writes_result_record(self, tmp_path, monkeypatch):
        """Successful execution persists a result record under .sac/sandbox_executions/."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is True

        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(result.proposal_id)
        assert record is not None
        assert record.status == "completed"
        assert record.executed is True
        assert record.exit_code == 0
        assert record.backend == "none"
        assert record.command_hash_prefix != ""
        assert len(record.command_hash_prefix) == 16

    def test_successful_execution_clears_pending(self, tmp_path, monkeypatch):
        """After successful execution, the pending proposal file is removed."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        gate.execute_pending()
        assert not gate.pending_path.exists()

    def test_non_zero_exit_writes_result_record(self, tmp_path, monkeypatch):
        """Non-zero exit still writes a completed result record."""
        from safecode.config import SafeCodeConfig

        gate = _setup_gate(tmp_path, monkeypatch)
        cfg = SafeCodeConfig()
        cfg.shell.allowed_commands = [sys.executable]
        cfg.shell.require_confirm_for_medium = False
        gate.config = cfg
        gate.propose(
            _make_plan(command=[sys.executable, "/tmp/nonexistent_script.py"]),
            "shell",
        )
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is True
        assert result.exit_code != 0

        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(result.proposal_id)
        assert record is not None
        assert record.status == "completed"
        assert record.executed is True
        assert record.exit_code != 0
        assert record.stdout_length >= 0
        assert record.stderr_length > 0

    def test_non_zero_exit_clears_pending(self, tmp_path, monkeypatch):
        """Non-zero exit clears pending — it's a terminal state."""
        from safecode.config import SafeCodeConfig

        gate = _setup_gate(tmp_path, monkeypatch)
        cfg = SafeCodeConfig()
        cfg.shell.allowed_commands = [sys.executable]
        cfg.shell.require_confirm_for_medium = False
        gate.config = cfg
        gate.propose(
            _make_plan(command=[sys.executable, "/tmp/nonexistent_script.py"]),
            "shell",
        )
        gate.approve()
        gate.execute_pending()
        assert not gate.pending_path.exists()

    def test_claim_failure_writes_result_record(self, tmp_path, monkeypatch):
        """Claim failure writes a blocked_claim result record."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        # Force claim_for_execution to return False while is_approved still
        # returns True so preflight passes.
        monkeypatch.setattr(
            SandboxExecutionApprovalStore,
            "claim_for_execution",
            lambda *a, **kw: False,
        )

        result = gate.execute_pending()
        assert result.executed is False

        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(result.proposal_id)
        assert record is not None
        assert record.status == "blocked_claim"
        assert record.executed is False
        assert record.exit_code is None
        assert "claim" in record.message.lower()

    def test_claim_failure_clears_pending(self, tmp_path, monkeypatch):
        """Claim failure clears pending — it's a terminal state not retriable."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        monkeypatch.setattr(
            SandboxExecutionApprovalStore,
            "claim_for_execution",
            lambda *a, **kw: False,
        )
        gate.execute_pending()
        assert not gate.pending_path.exists()

    def test_preflight_blocked_preserves_pending(self, tmp_path, monkeypatch):
        """Preflight blocked does NOT clear pending — user can fix and retry."""
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
        assert gate.pending_path.exists()

    def test_preflight_blocked_does_not_consume_approval(self, tmp_path, monkeypatch):
        """Preflight blocked still preserves the approval for retry."""
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
        gate.execute_pending()
        approval_store = SandboxExecutionApprovalStore(tmp_path)
        proposal = gate.load_pending()
        assert approval_store.is_approved(
            proposal.proposal_id,
            proposal.backend,
            proposal.command_hash,
            proposal.preview_hash,
        ) is True

    def test_claim_failure_does_not_call_shell_runner(self, tmp_path, monkeypatch):
        """Claim failure writes result without invoking subprocess."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        approval_store = SandboxExecutionApprovalStore(tmp_path)
        proposal = gate.load_pending()
        approval_store.consume(proposal.proposal_id)
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        result = gate.execute_pending()
        assert result.executed is False
        assert len(called) == 0

    def test_result_record_no_env_value_leak(self, tmp_path, monkeypatch):
        """Result record structured fields do not leak env values."""
        gate = _setup_gate(tmp_path, monkeypatch)
        monkeypatch.setenv("SECRET_TOKEN", "secret-value-123")
        gate.propose(_make_plan(env_keys=["SECRET_TOKEN"]), "shell")
        gate.approve()
        result = gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(result.proposal_id)
        payload = json.loads(
            store._path_for(result.proposal_id).read_text(encoding="utf-8")
        )
        combined = json.dumps(payload)
        assert "secret-value-123" not in combined
        assert "SECRET_TOKEN" not in combined

    def test_result_record_no_full_command_stored(self, tmp_path, monkeypatch):
        """Result record does NOT contain the full command — only hash + head."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "hello"]), "shell")
        gate.approve()
        result = gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(result.proposal_id)
        payload = json.loads(
            store._path_for(result.proposal_id).read_text(encoding="utf-8")
        )
        # "echo hello" as full argv must not appear in the record
        combined = json.dumps(payload)
        assert '["echo", "hello"]' not in combined

    def test_stdout_truncated_when_exceeds_limit(self, tmp_path, monkeypatch):
        """Output exceeding MAX_RESULT_PREVIEW_LENGTH is truncated."""
        from safecode.sandbox.execution import MAX_RESULT_PREVIEW_LENGTH
        from safecode.config import SafeCodeConfig

        gate = _setup_gate(tmp_path, monkeypatch)
        cfg = SafeCodeConfig()
        cfg.shell.allowed_commands = [sys.executable]
        cfg.shell.require_confirm_for_medium = False
        gate.config = cfg
        gate.propose(
            _make_plan(command=[sys.executable, "-c", "print('x' * 3000)"]),
            "shell",
        )
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is True
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(result.proposal_id)
        assert record.stdout_length == 3001  # 3000 x's + newline
        assert len(record.stdout_preview) < record.stdout_length
        assert "truncated" in record.stdout_preview.lower()

    def test_store_list_all_returns_records(self, tmp_path, monkeypatch):
        """list_all returns all stored result records sorted newest first."""
        gate = _setup_gate(tmp_path, monkeypatch)
        # Execute two proposals
        gate.propose(_make_plan(command=["echo", "first"]), "shell")
        gate.approve()
        r1 = gate.execute_pending()

        gate.propose(_make_plan(command=["echo", "second"]), "shell")
        gate.approve()
        r2 = gate.execute_pending()

        store = SandboxExecutionResultStore(tmp_path)
        records = store.list_all()
        assert len(records) >= 2
        # Newest first
        assert records[0].proposal_id == r2.proposal_id

    def test_store_latest_returns_most_recent(self, tmp_path, monkeypatch):
        """latest() returns the most recent result record."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "latest-test"]), "shell")
        gate.approve()
        result = gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        latest = store.latest()
        assert latest is not None
        assert latest.proposal_id == result.proposal_id

    def test_store_load_nonexistent_returns_none(self, tmp_path, monkeypatch):
        """load() returns None for unknown proposal_id."""
        _setup_gate(tmp_path, monkeypatch)
        store = SandboxExecutionResultStore(tmp_path)
        assert store.load("nonexistent-id") is None

    def test_discarded_pending_has_no_result(self, tmp_path, monkeypatch):
        """Manually discarding pending does NOT write a result record."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        proposal_id = gate.load_pending().proposal_id
        gate.discard()
        store = SandboxExecutionResultStore(tmp_path)
        assert store.load(proposal_id) is None


# ── D++++. Execution Result Robustness (v1.8.4) ──────────────────────────


class TestExecutionResultRobustness:
    """v1.8.4: result records include schema version, tolerate extra fields,
    and support filtering by backend/status/proposal_id."""

    def test_saved_record_has_schema_version(self, tmp_path, monkeypatch):
        """Result record JSON includes _schema_version field."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        result = gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        path = store._path_for(result.proposal_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["_schema_version"] == "v1"

    def test_old_record_without_schema_version_loads(self, tmp_path, monkeypatch):
        """Record missing _schema_version still loads successfully."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        result = gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        path = store._path_for(result.proposal_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["_schema_version"]
        path.write_text(json.dumps(data), encoding="utf-8")
        record = store.load(result.proposal_id)
        assert record is not None
        assert record.proposal_id == result.proposal_id

    def test_extra_unknown_fields_tolerated(self, tmp_path, monkeypatch):
        """Record with extra unknown JSON keys still loads successfully."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        result = gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        path = store._path_for(result.proposal_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_future_field_v99"] = "some unknown value"
        data["_another_extension"] = 42
        path.write_text(json.dumps(data), encoding="utf-8")
        record = store.load(result.proposal_id)
        assert record is not None
        assert record.proposal_id == result.proposal_id
        assert record.exit_code == 0

    def test_corrupt_json_returns_none(self, tmp_path, monkeypatch):
        """Corrupt JSON in result file returns None on load."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        result = gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        path = store._path_for(result.proposal_id)
        path.write_text("not valid json{{{", encoding="utf-8")
        assert store.load(result.proposal_id) is None

    def test_missing_required_fields_returns_none(self, tmp_path, monkeypatch):
        """Record missing required fields returns None on load."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(), "shell")
        gate.approve()
        result = gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        path = store._path_for(result.proposal_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["command_hash_prefix"]
        path.write_text(json.dumps(data), encoding="utf-8")
        assert store.load(result.proposal_id) is None

    def test_filter_by_backend(self, tmp_path, monkeypatch):
        """filter_by() correctly filters by backend."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "one"]), "shell")
        gate.approve()
        gate.execute_pending()

        store = SandboxExecutionResultStore(tmp_path)
        results = store.filter_by(backend="none")
        assert len(results) >= 1
        for r in results:
            assert r.backend == "none"

        empty = store.filter_by(backend="docker")
        assert len(empty) == 0

    def test_filter_by_status(self, tmp_path, monkeypatch):
        """filter_by() correctly filters by status."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "status-test"]), "shell")
        gate.approve()
        gate.execute_pending()

        store = SandboxExecutionResultStore(tmp_path)
        completed = store.filter_by(status="completed")
        assert len(completed) >= 1
        for r in completed:
            assert r.status == "completed"

        blocked = store.filter_by(status="blocked_claim")
        assert len(blocked) == 0

    def test_filter_by_proposal_id_substr(self, tmp_path, monkeypatch):
        """filter_by() correctly filters by proposal_id substring."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "substr-test"]), "shell")
        gate.approve()
        result = gate.execute_pending()

        store = SandboxExecutionResultStore(tmp_path)
        # Match by first 6 chars
        results = store.filter_by(proposal_id_substr=result.proposal_id[:6])
        assert len(results) >= 1
        assert results[0].proposal_id == result.proposal_id

        empty = store.filter_by(proposal_id_substr="zzz-nonexistent")
        assert len(empty) == 0

    def test_list_all_and_filter_by_same_ordering(self, tmp_path, monkeypatch):
        """filter_by() with no filters returns same results as list_all()."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "a"]), "shell")
        gate.approve()
        gate.execute_pending()
        gate.propose(_make_plan(command=["echo", "b"]), "shell")
        gate.approve()
        gate.execute_pending()

        store = SandboxExecutionResultStore(tmp_path)
        all_records = store.list_all()
        filtered = store.filter_by()
        assert len(filtered) == len(all_records)
        assert [r.proposal_id for r in filtered] == [r.proposal_id for r in all_records]

    def test_list_all_skips_corrupt_files(self, tmp_path, monkeypatch):
        """list_all() skips individual corrupt files without failing."""
        gate = _setup_gate(tmp_path, monkeypatch)
        gate.propose(_make_plan(command=["echo", "good"]), "shell")
        gate.approve()
        gate.execute_pending()

        store = SandboxExecutionResultStore(tmp_path)
        corrupt_path = store._dir / "corrupt.json"
        corrupt_path.write_text("{ not json }", encoding="utf-8")

        records = store.list_all()
        assert len(records) >= 1
        proposal_ids = [r.proposal_id for r in records]
        assert len(proposal_ids) > 0


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
