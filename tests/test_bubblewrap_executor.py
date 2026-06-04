"""Linux Bubblewrap executor tests for v2.4.2.

Covers LinuxBubblewrapExecutor success/fail-closed paths, shell=False,
preview_hash mismatch, missing bwrap, timeout, OSError, argv reconstruction
failure, audit/result lifecycle through SandboxExecutionGate, and
Noop/Docker/Seatbelt regressions.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import (
    LinuxBubblewrapAdapter,
    NoopSandboxAdapter,
    SandboxExecutionRequest,
)
from safecode.sandbox.bubblewrap import (
    BubblewrapArgsBuilder,
    BubblewrapExecutionResult,
    LinuxBubblewrapExecutor,
)
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability, SandboxCapabilityDetector
from safecode.sandbox.execution import (
    SandboxExecutionGate,
    SandboxExecutionProposal,
    SandboxExecutionResultStore,
)
from safecode.sandbox.executor_preflight import SandboxExecutorPreflight
from safecode.utils.time import utc_now_iso


# ── helpers ───────────────────────────────────────────────────────────────


def _make_bwrap_cap():
    return SandboxCapability(
        backend=SandboxBackend.LINUX_BUBBLEWRAP,
        available=True,
        supported_platforms=["Linux"],
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
    """Build a bwrap proposal via the adapter so preview_hash matches the argv."""
    cfg = config or SafeCodeConfig()
    cap = _make_bwrap_cap()
    adapter = LinuxBubblewrapAdapter(cap, project_root=tmp_path, config=cfg)
    req = _make_request(tmp_path)
    plan = adapter.build_plan(req)

    cmd = list(req.command)
    cmd_hash = hashlib.sha256(
        json.dumps(cmd, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    preview_hash = (
        hashlib.sha256(
            json.dumps(plan.args_preview, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if plan.args_preview
        else None
    )

    return SandboxExecutionProposal(
        proposal_id=str(uuid.uuid4()),
        created_at=utc_now_iso(),
        backend="linux_bubblewrap",
        command=cmd,
        command_hash=cmd_hash,
        purpose="shell",
        cwd=str(tmp_path),
        network_enabled=False,
        readonly_filesystem=True,
        writable_paths=[],
        env_keys=[],
        preview_kind="args",
        preview_hash=preview_hash,
    )


def _make_ok_run(*args, **kwargs):
    return SimpleNamespace(returncode=0, stdout=b"hello\n", stderr=b"")


def _make_plan_for_gate(tmp_path: Path):
    """Return a SandboxExecutionPlan suitable for gate.propose()."""
    cfg = SafeCodeConfig()
    cap = _make_bwrap_cap()
    adapter = LinuxBubblewrapAdapter(cap, project_root=tmp_path, config=cfg)
    req = _make_request(tmp_path)
    return adapter.build_plan(req)


# ── LinuxBubblewrapExecutor unit tests ───────────────────────────────────


class TestLinuxBubblewrapExecutorSuccess:
    def test_returns_executed_true_on_success(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)
        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=_make_ok_run)
        result = executor.execute(proposal)
        assert result.executed is True
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_message_contains_exit_code(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)
        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=_make_ok_run)
        result = executor.execute(proposal)
        assert "Exit code: 0" in result.message

    def test_nonzero_exit_code_still_executed(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)

        def run_fail(*args, **kwargs):
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"error output")

        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=run_fail)
        result = executor.execute(proposal)
        assert result.executed is True
        assert result.exit_code == 1

    def test_duration_ms_is_non_negative(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)
        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=_make_ok_run)
        result = executor.execute(proposal)
        assert result.duration_ms >= 0

    def test_bytes_stdout_decoded(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)

        def run_bytes(*args, **kwargs):
            return SimpleNamespace(returncode=0, stdout=b"bytes output\n", stderr=b"")

        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=run_bytes)
        result = executor.execute(proposal)
        assert isinstance(result.stdout, str)
        assert "bytes output" in result.stdout


class TestLinuxBubblewrapExecutorShellFalse:
    def test_run_called_with_shell_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)
        captured = {}

        def capturing_run(argv, **kwargs):
            captured["shell"] = kwargs.get("shell")
            captured["argv"] = argv
            return SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")

        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=capturing_run)
        executor.execute(proposal)
        assert captured["shell"] is False

    def test_argv_starts_with_bwrap(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)
        captured = {}

        def capturing_run(argv, **kwargs):
            captured["argv"] = argv
            return SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")

        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=capturing_run)
        executor.execute(proposal)
        assert captured["argv"][0] == "bwrap"

    def test_argv_ends_with_command(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)
        captured = {}

        def capturing_run(argv, **kwargs):
            captured["argv"] = argv
            return SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")

        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=capturing_run)
        executor.execute(proposal)
        # Command is appended after "--" separator in bwrap argv
        assert "echo" in captured["argv"]
        assert "hello" in captured["argv"]

    def test_no_shell_true_anywhere_in_kwargs(self, tmp_path, monkeypatch):
        """Confirm shell is never set to True."""
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)
        captured = {}

        def capturing_run(argv, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")

        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=capturing_run)
        executor.execute(proposal)
        assert captured["kwargs"].get("shell") is not True


class TestLinuxBubblewrapExecutorHashMismatch:
    def test_hash_mismatch_returns_executed_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)
        proposal = dataclasses.replace(proposal, preview_hash="deadbeef" * 8)
        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=_make_ok_run)
        result = executor.execute(proposal)
        assert result.executed is False

    def test_hash_mismatch_message_describes_problem(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)
        proposal = dataclasses.replace(proposal, preview_hash="deadbeef" * 8)
        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=_make_ok_run)
        result = executor.execute(proposal)
        assert "hash mismatch" in result.message.lower()

    def test_hash_mismatch_no_subprocess_called(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)
        proposal = dataclasses.replace(proposal, preview_hash="wronghash")
        called = []
        executor = LinuxBubblewrapExecutor(
            tmp_path, SafeCodeConfig(), run_fn=lambda *a, **kw: called.append(1)
        )
        executor.execute(proposal)
        assert len(called) == 0

    def test_none_preview_hash_skips_check(self, tmp_path, monkeypatch):
        """When preview_hash is None, hash verification is skipped."""
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)
        proposal = dataclasses.replace(proposal, preview_hash=None)
        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=_make_ok_run)
        result = executor.execute(proposal)
        assert result.executed is True


class TestLinuxBubblewrapExecutorMissingBwrap:
    def test_missing_binary_shutil_which_returns_executed_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: None)
        proposal = _build_proposal(tmp_path)
        called = []
        executor = LinuxBubblewrapExecutor(
            tmp_path, SafeCodeConfig(),
            run_fn=lambda *a, **kw: called.append(1),
        )
        result = executor.execute(proposal)
        assert result.executed is False
        assert "not found" in result.message.lower()
        assert len(called) == 0

    def test_file_not_found_from_subprocess_fails_closed(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)

        def raise_fnf(*args, **kwargs):
            raise FileNotFoundError("no bwrap")

        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=raise_fnf)
        result = executor.execute(proposal)
        assert result.executed is False
        assert "not found" in result.message.lower()


class TestLinuxBubblewrapExecutorTimeout:
    def test_timeout_returns_executed_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)

        def raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="bwrap", timeout=30)

        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=raise_timeout)
        result = executor.execute(proposal)
        assert result.executed is False
        assert "timed out" in result.message.lower()

    def test_timeout_message_contains_duration(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)

        def raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="bwrap", timeout=30)

        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=raise_timeout)
        result = executor.execute(proposal)
        assert "30s" in result.message


class TestLinuxBubblewrapExecutorOSError:
    def test_oserror_returns_executed_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)

        def raise_oserror(*args, **kwargs):
            raise OSError("permission denied")

        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=raise_oserror)
        result = executor.execute(proposal)
        assert result.executed is False
        assert "failed" in result.message.lower()

    def test_arbitrary_exception_fails_closed(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
        proposal = _build_proposal(tmp_path)

        def raise_random(*args, **kwargs):
            raise RuntimeError("unexpected error")

        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig(), run_fn=raise_random)
        result = executor.execute(proposal)
        assert result.executed is False
        assert result.exit_code is None


class TestLinuxBubblewrapExecutorArgvReconstruction:
    def test_argv_reconstruction_failure_fails_closed(self, tmp_path, monkeypatch):
        """If BubblewrapArgsBuilder raises, executor fails closed."""
        proposal = _build_proposal(tmp_path)

        def bad_builder_init(*args, **kwargs):
            raise RuntimeError("builder exploded")

        monkeypatch.setattr(
            "safecode.sandbox.bubblewrap.BubblewrapArgsBuilder.__init__",
            bad_builder_init,
        )
        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig())
        result = executor.execute(proposal)
        assert result.executed is False
        assert "reconstruction failed" in result.message.lower()

    def test_never_raises(self, tmp_path, monkeypatch):
        """execute() must not raise regardless of what goes wrong."""
        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: None)
        proposal = _build_proposal(tmp_path)
        executor = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig())
        result = executor.execute(proposal)
        assert isinstance(result, BubblewrapExecutionResult)


# ── Audit and result lifecycle via SandboxExecutionGate ──────────────────


class TestBubblewrapGateLifecycle:
    """v2.4.2 bwrap routing through SandboxExecutionGate."""

    def _setup_gate_with_bwrap_approval(self, tmp_path, monkeypatch):
        """Propose + approve a bwrap proposal; return gate and proposal_id."""
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
        monkeypatch.setenv("SAFECODE_SANDBOX_BUBBLEWRAP", "1")

        gate = SandboxExecutionGate(tmp_path)
        plan = _make_plan_for_gate(tmp_path)
        proposal = gate.propose(plan, "shell")
        gate.approve()
        self._patch_bwrap_available(monkeypatch)
        SandboxExecutorPreflight(tmp_path).run("bubblewrap")
        return gate, proposal.proposal_id

    def _patch_bwrap_available(self, monkeypatch):
        """Make preflight think bwrap backend is available and supports execution."""
        original_detect_all = SandboxCapabilityDetector.detect_all

        def patched(self_inner):
            caps = original_detect_all(self_inner)
            return [
                SandboxCapability(
                    backend=SandboxBackend.LINUX_BUBBLEWRAP,
                    available=True,
                    supported_platforms=["Linux"],
                    reason="mocked",
                )
                if cap.backend == SandboxBackend.LINUX_BUBBLEWRAP
                else cap
                for cap in caps
            ]

        monkeypatch.setattr(SandboxCapabilityDetector, "detect_all", patched)

    def _patch_bwrap_executor(self, monkeypatch, executed=True, exit_code=0):
        """Inject an ok or blocked executor result."""
        import safecode.sandbox.execution as exec_mod

        def fake_executor_class(project_root, config, run_fn=None):
            class _FakeExec:
                def execute(self, proposal):
                    return BubblewrapExecutionResult(
                        executed=executed,
                        exit_code=exit_code if executed else None,
                        stdout=b"ok" if executed else b"",
                        stderr=b"" if executed else b"blocked",
                        duration_ms=1,
                        message="ok" if executed else "bwrap unavailable",
                    )
            return _FakeExec()

        monkeypatch.setattr(
            "safecode.sandbox.bubblewrap.LinuxBubblewrapExecutor",
            fake_executor_class,
        )

    def test_bwrap_execution_writes_result_record(self, tmp_path, monkeypatch):
        gate, proposal_id = self._setup_gate_with_bwrap_approval(tmp_path, monkeypatch)
        self._patch_bwrap_available(monkeypatch)

        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")

        gate.execute_pending()

        result_store = SandboxExecutionResultStore(tmp_path)
        records = result_store.list_all()
        assert len(records) == 1
        assert records[0].backend == "linux_bubblewrap"

    def test_bwrap_execution_clears_pending(self, tmp_path, monkeypatch):
        gate, _ = self._setup_gate_with_bwrap_approval(tmp_path, monkeypatch)
        self._patch_bwrap_available(monkeypatch)

        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")

        gate.execute_pending()
        assert gate.load_pending() is None

    def test_bwrap_blocked_path_clears_pending(self, tmp_path, monkeypatch):
        """Even when bwrap is unavailable, pending is cleared after attempt."""
        gate, _ = self._setup_gate_with_bwrap_approval(tmp_path, monkeypatch)
        self._patch_bwrap_available(monkeypatch)

        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: None)

        gate.execute_pending()
        assert gate.load_pending() is None

    def test_bwrap_blocked_path_writes_result_record(self, tmp_path, monkeypatch):
        gate, _ = self._setup_gate_with_bwrap_approval(tmp_path, monkeypatch)
        self._patch_bwrap_available(monkeypatch)

        import safecode.sandbox.bubblewrap as bwrap_mod
        monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: None)

        gate.execute_pending()

        result_store = SandboxExecutionResultStore(tmp_path)
        records = result_store.list_all()
        assert len(records) == 1
        assert records[0].executed is False


# ── Adapter contract ─────────────────────────────────────────────────────


class TestLinuxBubblewrapAdapterSupportsExecution:
    def test_supports_execution_is_true(self):
        cap = _make_bwrap_cap()
        adapter = LinuxBubblewrapAdapter(cap)
        assert adapter.supports_execution() is True

    def test_build_plan_warnings_mention_v242(self, tmp_path):
        cap = _make_bwrap_cap()
        adapter = LinuxBubblewrapAdapter(cap, project_root=tmp_path)
        req = _make_request(tmp_path)
        plan = adapter.build_plan(req)
        warning_text = " ".join(plan.warnings)
        assert "v2.4.2" in warning_text

    def test_build_plan_no_longer_says_plan_only(self, tmp_path):
        cap = _make_bwrap_cap()
        adapter = LinuxBubblewrapAdapter(cap, project_root=tmp_path)
        req = _make_request(tmp_path)
        plan = adapter.build_plan(req)
        limitation_text = " ".join(plan.limitations)
        # Old "plan-only" text should not appear
        assert "plan-only" not in limitation_text.lower()
        assert "v1.7.2 does not execute" not in limitation_text


# ── Noop/Docker/Seatbelt regressions ────────────────────────────────────


class TestNoopBackendUnchanged:
    """Ensure Noop execution path is not affected."""

    def test_noop_supports_execution(self):
        assert NoopSandboxAdapter().supports_execution() is True

    def test_noop_gate_still_executes(self, tmp_path, monkeypatch):
        anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
        ad = tmp_path.parent / f"approvals-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))

        from safecode.sandbox.adapter import NoopSandboxAdapter, SandboxExecutionPlan
        gate = SandboxExecutionGate(tmp_path)

        noop_plan = SandboxExecutionPlan(
            backend=SandboxBackend.NONE,
            command=["true"],
            cwd=str(tmp_path),
            network_enabled=False,
            readonly_filesystem=True,
            writable_paths=[],
            env_keys=[],
            timeout_seconds=30,
        )
        proposal = gate.propose(noop_plan, "shell")
        gate.approve()

        result = gate.execute_pending()
        # Noop executes via ShellRunner — result.backend should be "none"
        assert result.backend == "none"


class TestDockerBackendUnchanged:
    """Ensure Docker adapter still supports execution after v2.4.2."""

    def test_docker_adapter_supports_execution(self):
        from safecode.sandbox.adapter import DockerSandboxAdapter

        cap = SandboxCapability(
            backend=SandboxBackend.DOCKER,
            available=True,
            supported_platforms=["Linux", "macOS"],
            reason="test",
        )
        adapter = DockerSandboxAdapter(cap)
        assert adapter.supports_execution() is True


class TestSeatbeltBackendUnchanged:
    """Ensure macOS Seatbelt adapter still supports execution after v2.4.2."""

    def test_seatbelt_adapter_supports_execution(self):
        from safecode.sandbox.adapter import MacOSSeatbeltAdapter

        cap = SandboxCapability(
            backend=SandboxBackend.MACOS_SEATBELT,
            available=True,
            supported_platforms=["macOS"],
            reason="test",
        )
        adapter = MacOSSeatbeltAdapter(cap)
        assert adapter.supports_execution() is True


# ── CLI honesty text ─────────────────────────────────────────────────────


class TestCLISandboxStatusWording:
    """Verify status output reflects v2.4.2 bubblewrap executing mode."""

    def test_status_panel_mentions_bubblewrap_executing(self, tmp_path, monkeypatch, capsys):
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["sandbox", "status"], catch_exceptions=False)
        output = result.output
        # Bubblewrap should now show as executing, not plan-only
        assert "executing" in output.lower() or "v2.4.2" in output

    def test_status_panel_no_longer_says_bubblewrap_plan_only(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["sandbox", "status"], catch_exceptions=False)
        # The old "Linux Bubblewrap: plan-only" line should be gone
        assert "Linux Bubblewrap: [yellow]plan-only" not in result.output
