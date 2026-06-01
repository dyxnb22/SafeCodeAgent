"""macOS Seatbelt executor tests for v2.4.1.

Covers MacOSSeatbeltExecutor success/fail-closed paths, shell=False,
preview_hash mismatch, missing sandbox-exec, timeout, OSError, audit/result
lifecycle through SandboxExecutionGate, and Noop/Docker regressions.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import (
    MacOSSeatbeltAdapter,
    NoopSandboxAdapter,
    SandboxExecutionRequest,
)
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability, SandboxCapabilityDetector
from safecode.sandbox.execution import (
    SandboxExecutionGate,
    SandboxExecutionProposal,
    SandboxExecutionResultStore,
)
from safecode.sandbox.seatbelt import (
    MacOSSeatbeltExecutor,
    SeatbeltExecutionResult,
    SeatbeltProfileBuilder,
)


# ── helpers ───────────────────────────────────────────────────────────────


def _make_seatbelt_cap():
    return SandboxCapability(
        backend=SandboxBackend.MACOS_SEATBELT,
        available=True,
        supported_platforms=["macOS"],
        reason="test",
        limitations=["test"],
    )


def _make_request(tmp_path: Path, **kwargs):
    defaults = {
        "command": ["echo", "hello"],
        "cwd": tmp_path,
        "purpose": "shell",
        "allow_network": False,
        "readonly_filesystem": True,
        "writable_paths": [],
        "env": {},
        "timeout_seconds": 30,
    }
    defaults.update(kwargs)
    return SandboxExecutionRequest(**defaults)


def _build_proposal(tmp_path: Path, config: SafeCodeConfig | None = None) -> SandboxExecutionProposal:
    """Build a seatbelt proposal via the adapter so preview_hash matches the profile."""
    cfg = config or SafeCodeConfig()
    cap = _make_seatbelt_cap()
    adapter = MacOSSeatbeltAdapter(cap, project_root=tmp_path, config=cfg)
    req = _make_request(tmp_path)
    plan = adapter.build_plan(req)

    import hashlib as _h
    from safecode.sandbox.execution import SandboxExecutionGate, _stable_json
    cmd = list(req.command)
    import json, uuid
    from safecode.utils.time import utc_now_iso
    cmd_hash = _h.sha256(json.dumps(cmd, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    preview_hash = _h.sha256(plan.profile_preview.encode("utf-8")).hexdigest() if plan.profile_preview else None

    return SandboxExecutionProposal(
        proposal_id=str(uuid.uuid4()),
        created_at=utc_now_iso(),
        backend="macos_seatbelt",
        command=cmd,
        command_hash=cmd_hash,
        purpose="shell",
        cwd=str(tmp_path),
        network_enabled=False,
        readonly_filesystem=True,
        writable_paths=[],
        env_keys=[],
        preview_kind="profile",
        preview_hash=preview_hash,
    )


def _make_ok_run(*args, **kwargs):
    return SimpleNamespace(returncode=0, stdout=b"hello\n", stderr=b"")


def _make_plan_for_gate(tmp_path: Path):
    """Return a SandboxExecutionPlan suitable for gate.propose()."""
    from safecode.sandbox.adapter import SandboxExecutionPlan
    cfg = SafeCodeConfig()
    cap = _make_seatbelt_cap()
    adapter = MacOSSeatbeltAdapter(cap, project_root=tmp_path, config=cfg)
    req = _make_request(tmp_path)
    return adapter.build_plan(req)


# ── MacOSSeatbeltExecutor unit tests ─────────────────────────────────────


class TestMacOSSeatbeltExecutorSuccess:
    def test_returns_executed_true_on_success(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)
        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=_make_ok_run)
        result = executor.execute(proposal)
        assert result.executed is True
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_message_contains_exit_code(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)
        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=_make_ok_run)
        result = executor.execute(proposal)
        assert "Exit code: 0" in result.message

    def test_nonzero_exit_code_still_executed(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)

        def run_fail(*args, **kwargs):
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"error output")

        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=run_fail)
        result = executor.execute(proposal)
        assert result.executed is True
        assert result.exit_code == 1

    def test_duration_ms_is_non_negative(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)
        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=_make_ok_run)
        result = executor.execute(proposal)
        assert result.duration_ms >= 0


class TestMacOSSeatbeltExecutorShellFalse:
    def test_run_called_with_shell_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)
        captured = {}

        def capturing_run(argv, **kwargs):
            captured["shell"] = kwargs.get("shell")
            captured["argv"] = argv
            return SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")

        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=capturing_run)
        executor.execute(proposal)
        assert captured["shell"] is False

    def test_argv_starts_with_sandbox_exec(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)
        captured = {}

        def capturing_run(argv, **kwargs):
            captured["argv"] = argv
            return SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")

        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=capturing_run)
        executor.execute(proposal)
        assert captured["argv"][0] == "sandbox-exec"
        assert captured["argv"][1] == "-p"

    def test_argv_ends_with_command(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)
        captured = {}

        def capturing_run(argv, **kwargs):
            captured["argv"] = argv
            return SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")

        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=capturing_run)
        executor.execute(proposal)
        # Command ["echo", "hello"] should appear at the end of argv
        assert captured["argv"][-2] == "echo"
        assert captured["argv"][-1] == "hello"


class TestMacOSSeatbeltExecutorHashMismatch:
    def test_hash_mismatch_returns_executed_false(self, tmp_path, monkeypatch):
        import dataclasses, safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)
        proposal = dataclasses.replace(proposal, preview_hash="deadbeef" * 8)
        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=_make_ok_run)
        result = executor.execute(proposal)
        assert result.executed is False

    def test_hash_mismatch_message_describes_problem(self, tmp_path, monkeypatch):
        import dataclasses, safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)
        proposal = dataclasses.replace(proposal, preview_hash="deadbeef" * 8)
        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=_make_ok_run)
        result = executor.execute(proposal)
        assert "hash mismatch" in result.message.lower()

    def test_hash_mismatch_no_subprocess_called(self, tmp_path, monkeypatch):
        import dataclasses, safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)
        proposal = dataclasses.replace(proposal, preview_hash="wronghash")
        called = []
        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=lambda *a, **kw: called.append(1))
        executor.execute(proposal)
        assert len(called) == 0

    def test_none_preview_hash_skips_check(self, tmp_path, monkeypatch):
        """When preview_hash is None, hash verification is skipped."""
        import dataclasses, safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)
        proposal = dataclasses.replace(proposal, preview_hash=None)
        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=_make_ok_run)
        result = executor.execute(proposal)
        assert result.executed is True


class TestMacOSSeatbeltExecutorMissingSandboxExec:
    def test_missing_binary_returns_executed_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: None)
        proposal = _build_proposal(tmp_path)
        called = []
        executor = MacOSSeatbeltExecutor(
            tmp_path, SafeCodeConfig(),
            run_fn=lambda *a, **kw: called.append(1),
        )
        result = executor.execute(proposal)
        assert result.executed is False
        assert "not found" in result.message.lower()
        assert len(called) == 0

    def test_file_not_found_from_subprocess_fails_closed(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)

        def raise_fnf(*args, **kwargs):
            raise FileNotFoundError("no sandbox-exec")

        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=raise_fnf)
        result = executor.execute(proposal)
        assert result.executed is False
        assert "not found" in result.message.lower()


class TestMacOSSeatbeltExecutorTimeout:
    def test_timeout_returns_executed_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)

        def raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="sandbox-exec", timeout=30)

        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=raise_timeout)
        result = executor.execute(proposal)
        assert result.executed is False
        assert "timed out" in result.message.lower()

    def test_timeout_message_contains_duration(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)

        def raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="sandbox-exec", timeout=30)

        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=raise_timeout)
        result = executor.execute(proposal)
        assert "30s" in result.message


class TestMacOSSeatbeltExecutorOSError:
    def test_oserror_returns_executed_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)

        def raise_oserror(*args, **kwargs):
            raise OSError("permission denied")

        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=raise_oserror)
        result = executor.execute(proposal)
        assert result.executed is False
        assert "failed" in result.message.lower()

    def test_arbitrary_exception_fails_closed(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        proposal = _build_proposal(tmp_path)

        def raise_random(*args, **kwargs):
            raise RuntimeError("unexpected error")

        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig(), run_fn=raise_random)
        result = executor.execute(proposal)
        assert result.executed is False
        assert result.exit_code is None


class TestMacOSSeatbeltExecutorProfileReconstruction:
    def test_profile_reconstruction_failure_fails_closed(self, tmp_path, monkeypatch):
        """If SeatbeltProfileBuilder raises, executor fails closed."""
        proposal = _build_proposal(tmp_path)

        def bad_builder_init(*args, **kwargs):
            raise RuntimeError("builder exploded")

        monkeypatch.setattr(
            "safecode.sandbox.seatbelt.SeatbeltProfileBuilder.__init__",
            bad_builder_init,
        )
        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig())
        result = executor.execute(proposal)
        assert result.executed is False
        assert "reconstruction failed" in result.message.lower()

    def test_never_raises(self, tmp_path, monkeypatch):
        """execute() must not raise regardless of what goes wrong."""
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: None)
        proposal = _build_proposal(tmp_path)
        executor = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig())
        # Should not raise
        result = executor.execute(proposal)
        assert isinstance(result, SeatbeltExecutionResult)


# ── Audit and result lifecycle via SandboxExecutionGate ───────────────────


class TestSeatbeltGateLifecycle:
    """v2.4.1 seatbelt routing through SandboxExecutionGate."""

    def _setup_gate_with_seatbelt_approval(self, tmp_path, monkeypatch):
        """Propose + approve a seatbelt proposal; return gate and proposal_id."""
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))

        gate = SandboxExecutionGate(tmp_path)
        plan = _make_plan_for_gate(tmp_path)
        proposal = gate.propose(plan, "shell")
        gate.approve()
        return gate, proposal.proposal_id

    def _patch_seatbelt_available(self, monkeypatch):
        """Make preflight think seatbelt backend is available."""
        original_detect_all = SandboxCapabilityDetector.detect_all

        def patched(self_inner):
            caps = original_detect_all(self_inner)
            return [
                SandboxCapability(
                    backend=SandboxBackend.MACOS_SEATBELT,
                    available=True,
                    supported_platforms=["macOS"],
                    reason="mocked",
                )
                if cap.backend == SandboxBackend.MACOS_SEATBELT
                else cap
                for cap in caps
            ]

        monkeypatch.setattr(SandboxCapabilityDetector, "detect_all", patched)

    def _ok_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")

    def test_seatbelt_execution_writes_result_record(self, tmp_path, monkeypatch):
        gate, proposal_id = self._setup_gate_with_seatbelt_approval(tmp_path, monkeypatch)
        self._patch_seatbelt_available(monkeypatch)
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        monkeypatch.setattr(seatbelt_mod.subprocess, "run", self._ok_run)

        gate.execute_pending()

        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(proposal_id)
        assert record is not None
        assert record.backend == "macos_seatbelt"

    def test_seatbelt_execution_clears_pending(self, tmp_path, monkeypatch):
        gate, proposal_id = self._setup_gate_with_seatbelt_approval(tmp_path, monkeypatch)
        self._patch_seatbelt_available(monkeypatch)
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        monkeypatch.setattr(seatbelt_mod.subprocess, "run", self._ok_run)

        gate.execute_pending()
        assert not gate.pending_path.exists()

    def test_seatbelt_blocked_still_clears_pending(self, tmp_path, monkeypatch):
        """Even when execution fails (e.g. sandbox-exec missing), pending is cleared."""
        gate, proposal_id = self._setup_gate_with_seatbelt_approval(tmp_path, monkeypatch)
        self._patch_seatbelt_available(monkeypatch)
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: None)

        result = gate.execute_pending()

        assert result.executed is False
        assert not gate.pending_path.exists()

    def test_seatbelt_blocked_writes_result_record(self, tmp_path, monkeypatch):
        gate, proposal_id = self._setup_gate_with_seatbelt_approval(tmp_path, monkeypatch)
        self._patch_seatbelt_available(monkeypatch)
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: None)

        gate.execute_pending()

        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(proposal_id)
        assert record is not None
        assert record.backend == "macos_seatbelt"
        assert record.executed is False

    def test_seatbelt_writes_audit_events(self, tmp_path, monkeypatch):
        from safecode.audit.logger import AuditLogger
        gate, proposal_id = self._setup_gate_with_seatbelt_approval(tmp_path, monkeypatch)
        self._patch_seatbelt_available(monkeypatch)
        import safecode.sandbox.seatbelt as seatbelt_mod
        monkeypatch.setattr(seatbelt_mod.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        monkeypatch.setattr(seatbelt_mod.subprocess, "run", self._ok_run)

        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=20)
        types = [e.type for e in events]
        assert "sandbox_execution_approval_claimed" in types
        assert any(t in ("sandbox_execution_completed", "sandbox_execution_blocked") for t in types)


# ── Noop/Docker regression ────────────────────────────────────────────────


class TestNoopDockerRegressionAfterSeatbelt:
    """Noop and Docker execution paths must be unaffected by seatbelt addition."""

    def test_noop_still_executes(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))

        from safecode.sandbox.adapter import SandboxExecutionPlan
        plan = SandboxExecutionPlan(
            backend=SandboxBackend.NONE,
            command=["echo", "hello"],
            cwd=str(tmp_path),
            network_enabled=False,
            readonly_filesystem=True,
            writable_paths=[],
            env_keys=[],
            timeout_seconds=30,
            profile_preview=None,
            args_preview=[],
            container_preview=[],
        )
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(plan, "shell")
        gate.approve()
        result = gate.execute_pending()
        assert result.executed is True
        assert result.exit_code == 0

    def test_docker_still_blocked_when_daemon_unavailable(self, tmp_path, monkeypatch):
        from safecode.sandbox.docker import DockerDaemonChecker, DockerContainerPlanBuilder
        from safecode.sandbox.adapter import SandboxExecutionPlan, SandboxExecutionRequest

        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))

        req = SandboxExecutionRequest(
            command=["echo", "hello"], cwd=tmp_path, purpose="shell",
            allow_network=False, readonly_filesystem=True, writable_paths=[], env={}, timeout_seconds=30,
        )
        docker_plan_obj = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(req)
        plan = SandboxExecutionPlan(
            backend=SandboxBackend.DOCKER,
            command=["echo", "hello"],
            cwd=str(tmp_path),
            network_enabled=False,
            readonly_filesystem=True,
            writable_paths=[],
            env_keys=[],
            timeout_seconds=30,
            profile_preview=None,
            args_preview=[],
            container_preview=docker_plan_obj.argv,
        )
        gate = SandboxExecutionGate(tmp_path)
        gate.propose(plan, "shell")
        gate.approve()

        original_detect_all = SandboxCapabilityDetector.detect_all

        def patched_detect_all(self_inner):
            caps = original_detect_all(self_inner)
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
        monkeypatch.setattr(DockerDaemonChecker, "check", lambda self: (False, "no daemon in test"))

        result = gate.execute_pending()
        assert result.executed is False
        assert "unavailable" in result.message.lower()


# ── MacOSSeatbeltAdapter.supports_execution() ─────────────────────────────


class TestMacOSSeatbeltAdapterSupportsExecution:
    def test_supports_execution_returns_true(self):
        cap = _make_seatbelt_cap()
        adapter = MacOSSeatbeltAdapter(cap)
        assert adapter.supports_execution() is True

    def test_linux_bubblewrap_still_plan_only(self):
        from safecode.sandbox.adapter import LinuxBubblewrapAdapter
        cap = SandboxCapability(
            backend=SandboxBackend.LINUX_BUBBLEWRAP,
            available=True,
            supported_platforms=["Linux"],
            reason="test",
        )
        adapter = LinuxBubblewrapAdapter(cap)
        assert adapter.supports_execution() is False

    def test_preflight_error_message_no_longer_says_seatbelt(self, tmp_path, monkeypatch):
        """preflight error message should not say 'macOS Seatbelt' is plan-only."""
        from safecode.sandbox.preflight import SandboxExecutionPreflight
        from safecode.sandbox.execution import SandboxExecutionProposalStore, SandboxExecutionProposal
        from safecode.utils.time import utc_now_iso
        import uuid, json, hashlib

        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))

        # Create a proposal with macos_seatbelt backend
        cmd = ["echo", "hello"]
        cmd_hash = hashlib.sha256(json.dumps(cmd, separators=(",", ":")).encode()).hexdigest()
        proposal = SandboxExecutionProposal(
            proposal_id=str(uuid.uuid4()),
            created_at=utc_now_iso(),
            backend="macos_seatbelt",
            command=cmd,
            command_hash=cmd_hash,
            purpose="shell",
            cwd=str(tmp_path),
            network_enabled=False,
            readonly_filesystem=True,
            writable_paths=[],
            env_keys=[],
            preview_kind="none",
            preview_hash=None,
        )
        store = SandboxExecutionProposalStore(tmp_path)
        store.create(proposal)

        preflight = SandboxExecutionPreflight(tmp_path)
        result = preflight.run()

        combined = " ".join(result.reasons)
        assert "macOS Seatbelt" not in combined or "plan-only" not in combined
