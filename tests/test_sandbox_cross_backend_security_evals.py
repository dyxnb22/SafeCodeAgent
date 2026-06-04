"""Cross-backend security evaluation suite for v2.4.3.

Verifies security invariants that must hold uniformly across all three real
execution backends: Docker, macOS Seatbelt, and Linux Bubblewrap.

All tests are platform-stable: they use injected run functions, monkeypatched
capability detectors, and mocked binary checkers — no real Docker daemon,
sandbox-exec, or bwrap binary is required.

Invariants tested:
  A. shell=False enforced for every real subprocess backend.
  B. preview_hash mismatch blocks before binary/daemon check.
  C. Network disabled by default in all three plan outputs.
  D. --privileged never appears in Docker argv.
  E. Env values not leaked into generated argv, profile text, or bwrap argv.
  F. Filesystem boundary: writable paths outside project root rejected.
  G. Sensitive paths (.ssh, .env, .aws) never granted write access.
  H. Approval atomically claimed before executor is invoked.
  I. Result record written and pending cleared for every terminal attempt.
  J. Env values not present in audit records for any real backend.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from safecode.audit.logger import AuditLogger
from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import (
    DockerSandboxAdapter,
    LinuxBubblewrapAdapter,
    MacOSSeatbeltAdapter,
    SandboxExecutionRequest,
)
from safecode.sandbox.approvals import SandboxExecutionApprovalStore
from safecode.sandbox.bubblewrap import (
    BubblewrapArgsBuilder,
    LinuxBubblewrapExecutor,
)
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability, SandboxCapabilityDetector
from safecode.sandbox.docker import DockerContainerPlanBuilder, DockerDaemonChecker, DockerExecutor
from safecode.sandbox.execution import (
    SandboxExecutionGate,
    SandboxExecutionProposal,
    SandboxExecutionResultStore,
)
from safecode.sandbox.executor_preflight import SandboxExecutorPreflight
from safecode.sandbox.seatbelt import MacOSSeatbeltExecutor, SeatbeltProfileBuilder
from safecode.utils.time import utc_now_iso


# ── shared helpers ────────────────────────────────────────────────────────


def _make_request(tmp_path: Path, **kwargs) -> SandboxExecutionRequest:
    defaults = dict(
        command=["echo", "hello"],
        cwd=tmp_path,
        purpose="test",
        allow_network=False,
        readonly_filesystem=True,
        writable_paths=[],
        env={},
        timeout_seconds=30,
    )
    defaults.update(kwargs)
    return SandboxExecutionRequest(**defaults)


def _cmd_hash(cmd: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(cmd, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _list_hash(lst: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(lst, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _base_proposal(**kwargs) -> SandboxExecutionProposal:
    defaults = dict(
        proposal_id=str(uuid4()),
        created_at=utc_now_iso(),
        backend="none",
        command=["echo", "hello"],
        command_hash=_cmd_hash(["echo", "hello"]),
        purpose="test",
        cwd="/tmp/test",
        network_enabled=False,
        readonly_filesystem=True,
        writable_paths=[],
        env_keys=[],
        preview_kind="none",
        preview_hash=None,
    )
    defaults.update(kwargs)
    return SandboxExecutionProposal(**defaults)


def _docker_proposal(tmp_path: Path, **kwargs) -> SandboxExecutionProposal:
    """Build a Docker proposal whose preview_hash matches the real container plan."""
    cfg = SafeCodeConfig()
    cmd = list(kwargs.get("command", ["echo", "hello"]))
    req = _make_request(tmp_path, command=cmd, allow_network=kwargs.get("allow_network", False))
    plan = DockerContainerPlanBuilder(tmp_path, cfg).build(req)
    return _base_proposal(
        backend="docker",
        command=cmd,
        command_hash=_cmd_hash(cmd),
        cwd=str(tmp_path),
        network_enabled=req.allow_network,
        env_keys=list(kwargs.get("env_keys", [])),
        preview_kind="container",
        preview_hash=_list_hash(plan.argv),
    )


def _seatbelt_proposal(tmp_path: Path, **kwargs) -> SandboxExecutionProposal:
    """Build a Seatbelt proposal whose preview_hash matches the real profile."""
    cfg = SafeCodeConfig()
    cmd = list(kwargs.get("command", ["echo", "hello"]))
    req = _make_request(tmp_path, command=cmd, allow_network=kwargs.get("allow_network", False))
    plan = SeatbeltProfileBuilder(tmp_path, cfg).build(req)
    return _base_proposal(
        backend="macos_seatbelt",
        command=cmd,
        command_hash=_cmd_hash(cmd),
        cwd=str(tmp_path),
        network_enabled=req.allow_network,
        env_keys=list(kwargs.get("env_keys", [])),
        preview_kind="profile",
        preview_hash=_text_hash(plan.profile_text),
    )


def _bwrap_proposal(tmp_path: Path, **kwargs) -> SandboxExecutionProposal:
    """Build a Bubblewrap proposal whose preview_hash matches the real argv."""
    cfg = SafeCodeConfig()
    cmd = list(kwargs.get("command", ["echo", "hello"]))
    req = _make_request(tmp_path, command=cmd, allow_network=kwargs.get("allow_network", False))
    plan = BubblewrapArgsBuilder(tmp_path, cfg).build(req)
    return _base_proposal(
        backend="linux_bubblewrap",
        command=cmd,
        command_hash=_cmd_hash(cmd),
        cwd=str(tmp_path),
        network_enabled=req.allow_network,
        env_keys=list(kwargs.get("env_keys", [])),
        preview_kind="args",
        preview_hash=_list_hash(plan.argv),
    )


_OK_RUN = lambda *a, **kw: SimpleNamespace(returncode=0, stdout=b"ok\n", stderr=b"")


def _setup_base_gate(tmp_path: Path, monkeypatch) -> SandboxExecutionGate:
    ad = tmp_path.parent / f"approvals-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(ad))
    anchor = tmp_path.parent / f"anchors-{tmp_path.name}"
    monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor))
    return SandboxExecutionGate(tmp_path)


def _mock_backend_available(monkeypatch, target_backend: SandboxBackend) -> None:
    """Monkeypatch SandboxCapabilityDetector so target_backend reports available=True."""
    original = SandboxCapabilityDetector.detect_all

    def patched(self):
        caps = original(self)
        return [
            SandboxCapability(
                backend=target_backend,
                available=True,
                supported_platforms=["all"],
                reason="mocked available for test",
            )
            if cap.backend == target_backend
            else cap
            for cap in caps
        ]

    monkeypatch.setattr(SandboxCapabilityDetector, "detect_all", patched)


def _setup_docker_gate(tmp_path: Path, monkeypatch, run_fn=None):
    """Gate with an approved Docker proposal; all mocks applied."""
    gate = _setup_base_gate(tmp_path, monkeypatch)
    docker_cap = SandboxCapability(
        backend=SandboxBackend.DOCKER, available=True, supported_platforms=["all"], reason="test"
    )
    adapter = DockerSandboxAdapter(docker_cap, project_root=tmp_path, config=SafeCodeConfig())
    req = _make_request(tmp_path)
    plan = adapter.build_plan(req)
    proposal = gate.propose(plan, "test")
    gate.approve()
    _mock_backend_available(monkeypatch, SandboxBackend.DOCKER)
    monkeypatch.setenv("SAFECODE_SANDBOX_DOCKER", "1")
    SandboxExecutorPreflight(tmp_path).run("docker")
    monkeypatch.setattr(DockerDaemonChecker, "check", lambda self: (True, ""))
    if run_fn is not None:
        import safecode.sandbox.docker as _m
        monkeypatch.setattr(_m.subprocess, "run", run_fn)
    return gate, proposal.proposal_id


def _setup_seatbelt_gate(tmp_path: Path, monkeypatch, run_fn=None):
    """Gate with an approved Seatbelt proposal; all mocks applied."""
    gate = _setup_base_gate(tmp_path, monkeypatch)
    seatbelt_cap = SandboxCapability(
        backend=SandboxBackend.MACOS_SEATBELT, available=True, supported_platforms=["darwin"], reason="test"
    )
    adapter = MacOSSeatbeltAdapter(seatbelt_cap, project_root=tmp_path, config=SafeCodeConfig())
    req = _make_request(tmp_path)
    plan = adapter.build_plan(req)
    proposal = gate.propose(plan, "test")
    gate.approve()
    _mock_backend_available(monkeypatch, SandboxBackend.MACOS_SEATBELT)
    monkeypatch.setenv("SAFECODE_SANDBOX_SEATBELT", "1")
    SandboxExecutorPreflight(tmp_path).run("seatbelt")
    import safecode.sandbox.seatbelt as _sm
    monkeypatch.setattr(_sm.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
    if run_fn is not None:
        monkeypatch.setattr(_sm.subprocess, "run", run_fn)
    return gate, proposal.proposal_id


def _setup_bwrap_gate(tmp_path: Path, monkeypatch, run_fn=None):
    """Gate with an approved Bubblewrap proposal; all mocks applied."""
    gate = _setup_base_gate(tmp_path, monkeypatch)
    bwrap_cap = SandboxCapability(
        backend=SandboxBackend.LINUX_BUBBLEWRAP, available=True, supported_platforms=["linux"], reason="test"
    )
    adapter = LinuxBubblewrapAdapter(bwrap_cap, project_root=tmp_path, config=SafeCodeConfig())
    req = _make_request(tmp_path)
    plan = adapter.build_plan(req)
    proposal = gate.propose(plan, "test")
    gate.approve()
    _mock_backend_available(monkeypatch, SandboxBackend.LINUX_BUBBLEWRAP)
    monkeypatch.setenv("SAFECODE_SANDBOX_BUBBLEWRAP", "1")
    SandboxExecutorPreflight(tmp_path).run("bubblewrap")
    import safecode.sandbox.bubblewrap as _bm
    monkeypatch.setattr(_bm.shutil, "which", lambda name: "/usr/bin/bwrap")
    if run_fn is not None:
        monkeypatch.setattr(_bm.subprocess, "run", run_fn)
    return gate, proposal.proposal_id


# ── A. shell=False enforced ───────────────────────────────────────────────


class TestCrossBackendShellFalse:
    """shell=False must be passed to every real subprocess.run call.

    Tests inject a recording run_fn and verify shell was not True.
    Backend binary/daemon are also mocked so execution reaches subprocess.run.
    """

    def test_docker_shell_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.docker as _m

        recorded: list[dict] = []

        def record_run(*args, **kwargs):
            recorded.append({"args": args, "kwargs": kwargs})
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        proposal = _docker_proposal(tmp_path)
        monkeypatch.setattr(DockerDaemonChecker, "check", lambda self: (True, ""))
        monkeypatch.setattr(_m.subprocess, "run", record_run)
        DockerExecutor(tmp_path, SafeCodeConfig()).execute(proposal)

        assert len(recorded) == 1
        assert recorded[0]["kwargs"].get("shell") is not True

    def test_seatbelt_shell_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as _sm

        recorded: list[dict] = []

        def record_run(*args, **kwargs):
            recorded.append({"args": args, "kwargs": kwargs})
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        proposal = _seatbelt_proposal(tmp_path)
        monkeypatch.setattr(_sm.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        monkeypatch.setattr(_sm.subprocess, "run", record_run)
        MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig()).execute(proposal)

        assert len(recorded) == 1
        assert recorded[0]["kwargs"].get("shell") is not True

    def test_bubblewrap_shell_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as _bm

        recorded: list[dict] = []

        def record_run(*args, **kwargs):
            recorded.append({"args": args, "kwargs": kwargs})
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        proposal = _bwrap_proposal(tmp_path)
        monkeypatch.setattr(_bm.shutil, "which", lambda name: "/usr/bin/bwrap")
        monkeypatch.setattr(_bm.subprocess, "run", record_run)
        LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig()).execute(proposal)

        assert len(recorded) == 1
        assert recorded[0]["kwargs"].get("shell") is not True

    def test_docker_shell_kwarg_explicitly_false(self, tmp_path, monkeypatch):
        """Docker subprocess.run call must pass shell=False explicitly."""
        import safecode.sandbox.docker as _m

        recorded: list[dict] = []

        def record_run(*args, **kwargs):
            recorded.append(kwargs)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        proposal = _docker_proposal(tmp_path)
        monkeypatch.setattr(DockerDaemonChecker, "check", lambda self: (True, ""))
        monkeypatch.setattr(_m.subprocess, "run", record_run)
        DockerExecutor(tmp_path, SafeCodeConfig()).execute(proposal)

        assert recorded[0].get("shell") is False

    def test_seatbelt_shell_kwarg_explicitly_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as _sm

        recorded: list[dict] = []

        def record_run(*args, **kwargs):
            recorded.append(kwargs)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        proposal = _seatbelt_proposal(tmp_path)
        monkeypatch.setattr(_sm.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        monkeypatch.setattr(_sm.subprocess, "run", record_run)
        MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig()).execute(proposal)

        assert recorded[0].get("shell") is False

    def test_bubblewrap_shell_kwarg_explicitly_false(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as _bm

        recorded: list[dict] = []

        def record_run(*args, **kwargs):
            recorded.append(kwargs)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        proposal = _bwrap_proposal(tmp_path)
        monkeypatch.setattr(_bm.shutil, "which", lambda name: "/usr/bin/bwrap")
        monkeypatch.setattr(_bm.subprocess, "run", record_run)
        LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig()).execute(proposal)

        assert recorded[0].get("shell") is False


# ── B. preview_hash mismatch blocks before binary/daemon check ────────────


class TestCrossBackendHashBeforeBinaryCheck:
    """preview_hash mismatch must block execution before any binary or daemon
    check is performed.  Tests verify the binary/daemon check is never reached
    when the hash does not match the rebuilt plan.
    """

    def test_docker_hash_mismatch_daemon_not_checked(self, tmp_path, monkeypatch):
        import safecode.sandbox.docker as _m

        daemon_calls: list[bool] = []

        def never_called(self):
            daemon_calls.append(True)
            return (True, "")

        proposal = _docker_proposal(tmp_path)
        # Corrupt the hash
        import dataclasses
        bad_proposal = dataclasses.replace(proposal, preview_hash="0" * 64)
        monkeypatch.setattr(DockerDaemonChecker, "check", never_called)
        result = DockerExecutor(tmp_path, SafeCodeConfig()).execute(bad_proposal)
        assert result.executed is False
        assert "mismatch" in result.message.lower()
        assert len(daemon_calls) == 0

    def test_seatbelt_hash_mismatch_which_not_called(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as _sm

        which_calls: list[str] = []

        def track_which(name: str):
            which_calls.append(name)
            return "/usr/bin/sandbox-exec"

        import dataclasses
        proposal = _seatbelt_proposal(tmp_path)
        bad_proposal = dataclasses.replace(proposal, preview_hash="0" * 64)
        monkeypatch.setattr(_sm.shutil, "which", track_which)
        result = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig()).execute(bad_proposal)
        assert result.executed is False
        assert "mismatch" in result.message.lower()
        assert len(which_calls) == 0

    def test_bubblewrap_hash_mismatch_which_not_called(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as _bm

        which_calls: list[str] = []

        def track_which(name: str):
            which_calls.append(name)
            return "/usr/bin/bwrap"

        import dataclasses
        proposal = _bwrap_proposal(tmp_path)
        bad_proposal = dataclasses.replace(proposal, preview_hash="0" * 64)
        monkeypatch.setattr(_bm.shutil, "which", track_which)
        result = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig()).execute(bad_proposal)
        assert result.executed is False
        assert "mismatch" in result.message.lower()
        assert len(which_calls) == 0

    def test_docker_hash_mismatch_no_subprocess(self, tmp_path, monkeypatch):
        import safecode.sandbox.docker as _m
        import dataclasses

        calls: list = []
        proposal = _docker_proposal(tmp_path)
        bad_proposal = dataclasses.replace(proposal, preview_hash="0" * 64)
        monkeypatch.setattr(DockerDaemonChecker, "check", lambda self: (True, ""))
        monkeypatch.setattr(_m.subprocess, "run", lambda *a, **kw: calls.append(1))
        result = DockerExecutor(tmp_path, SafeCodeConfig()).execute(bad_proposal)
        assert result.executed is False
        assert len(calls) == 0

    def test_seatbelt_hash_mismatch_no_subprocess(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as _sm
        import dataclasses

        calls: list = []
        proposal = _seatbelt_proposal(tmp_path)
        bad_proposal = dataclasses.replace(proposal, preview_hash="0" * 64)
        monkeypatch.setattr(_sm.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        monkeypatch.setattr(_sm.subprocess, "run", lambda *a, **kw: calls.append(1))
        result = MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig()).execute(bad_proposal)
        assert result.executed is False
        assert len(calls) == 0

    def test_bubblewrap_hash_mismatch_no_subprocess(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as _bm
        import dataclasses

        calls: list = []
        proposal = _bwrap_proposal(tmp_path)
        bad_proposal = dataclasses.replace(proposal, preview_hash="0" * 64)
        monkeypatch.setattr(_bm.shutil, "which", lambda name: "/usr/bin/bwrap")
        monkeypatch.setattr(_bm.subprocess, "run", lambda *a, **kw: calls.append(1))
        result = LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig()).execute(bad_proposal)
        assert result.executed is False
        assert len(calls) == 0


# ── C. Network disabled by default ───────────────────────────────────────


class TestCrossBackendNetworkDisabledDefault:
    """Network isolation must be the default for all three real backends.

    Docker: '--network none' appears in argv.
    Seatbelt: 'network-outbound' does not appear in the default profile.
    Bubblewrap: '--unshare-net' appears in argv.
    """

    def test_docker_network_none_in_argv_by_default(self, tmp_path):
        req = _make_request(tmp_path, allow_network=False)
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert "--network" in plan.argv
        idx = plan.argv.index("--network")
        assert plan.argv[idx + 1] == "none"

    def test_docker_no_network_none_when_enabled(self, tmp_path):
        cfg = SafeCodeConfig()
        cfg.sandbox.network_enabled = True
        req = _make_request(tmp_path, allow_network=True)
        plan = DockerContainerPlanBuilder(tmp_path, cfg).build(req)
        pair = any(
            plan.argv[i] == "--network" and plan.argv[i + 1] == "none"
            for i in range(len(plan.argv) - 1)
        )
        assert not pair

    def test_seatbelt_no_network_outbound_by_default(self, tmp_path):
        req = _make_request(tmp_path, allow_network=False)
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert "network-outbound" not in plan.profile_text

    def test_seatbelt_network_disabled_comment_in_profile(self, tmp_path):
        req = _make_request(tmp_path, allow_network=False)
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert "DISABLED" in plan.profile_text.upper() or "network" in plan.profile_text

    def test_bubblewrap_unshare_net_in_argv_by_default(self, tmp_path):
        req = _make_request(tmp_path, allow_network=False)
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert "--unshare-net" in plan.argv

    def test_bubblewrap_no_unshare_net_when_network_enabled(self, tmp_path):
        cfg = SafeCodeConfig()
        cfg.sandbox.network_enabled = True
        req = _make_request(tmp_path, allow_network=True)
        plan = BubblewrapArgsBuilder(tmp_path, cfg).build(req)
        assert "--unshare-net" not in plan.argv

    def test_docker_network_none_appears_before_image(self, tmp_path):
        req = _make_request(tmp_path, allow_network=False)
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(req)
        from safecode.sandbox.docker import DEFAULT_IMAGE
        img_idx = plan.argv.index(DEFAULT_IMAGE)
        net_idx = plan.argv.index("--network")
        assert net_idx < img_idx


# ── D. Docker-specific: --privileged never present ───────────────────────


class TestDockerPrivilegedNeverPresent:
    """--privileged must never appear in Docker argv under any configuration."""

    def test_no_privileged_in_default_plan(self, tmp_path):
        req = _make_request(tmp_path)
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert "--privileged" not in plan.argv

    def test_no_privileged_with_writable_paths(self, tmp_path):
        writable = tmp_path / "output"
        writable.mkdir()
        req = _make_request(
            tmp_path, readonly_filesystem=False, writable_paths=[writable]
        )
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert "--privileged" not in plan.argv

    def test_no_privileged_with_network_enabled(self, tmp_path):
        cfg = SafeCodeConfig()
        cfg.sandbox.network_enabled = True
        req = _make_request(tmp_path, allow_network=True)
        plan = DockerContainerPlanBuilder(tmp_path, cfg).build(req)
        assert "--privileged" not in plan.argv

    def test_no_privileged_readonly_false(self, tmp_path):
        req = _make_request(tmp_path, readonly_filesystem=False)
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert "--privileged" not in plan.argv


# ── E. Env values not leaked ─────────────────────────────────────────────


class TestCrossBackendEnvNotLeaked:
    """Env values must not appear in generated argv, profile text, or audit records.

    Each executor reconstructs the plan using env={}, so process env values
    and any values behind env_keys cannot propagate into the execution path.
    """

    def test_docker_env_value_not_in_argv(self, tmp_path, monkeypatch):
        import safecode.sandbox.docker as _m

        monkeypatch.setenv("CROSS_BACKEND_SECRET", "cross-secret-xyz-999")
        recorded_argv: list[list[str]] = []

        def record_run(argv, **kwargs):
            recorded_argv.append(list(argv))
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        proposal = _docker_proposal(tmp_path, env_keys=["CROSS_BACKEND_SECRET"])
        monkeypatch.setattr(DockerDaemonChecker, "check", lambda self: (True, ""))
        monkeypatch.setattr(_m.subprocess, "run", record_run)
        DockerExecutor(tmp_path, SafeCodeConfig()).execute(proposal)

        full_argv = " ".join(recorded_argv[0]) if recorded_argv else ""
        assert "cross-secret-xyz-999" not in full_argv

    def test_seatbelt_env_value_not_in_profile(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as _sm

        monkeypatch.setenv("CROSS_BACKEND_SECRET", "seatbelt-secret-xyz-999")

        recorded_argv: list[list[str]] = []

        def record_run(argv, **kwargs):
            recorded_argv.append(list(argv))
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        proposal = _seatbelt_proposal(tmp_path, env_keys=["CROSS_BACKEND_SECRET"])
        monkeypatch.setattr(_sm.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        monkeypatch.setattr(_sm.subprocess, "run", record_run)
        MacOSSeatbeltExecutor(tmp_path, SafeCodeConfig()).execute(proposal)

        # The second argv element is the profile text in sandbox-exec -p <profile> <cmd>
        if len(recorded_argv) > 0 and len(recorded_argv[0]) > 2:
            profile_arg = recorded_argv[0][2]
            assert "seatbelt-secret-xyz-999" not in profile_arg
        full_argv_str = " ".join(recorded_argv[0]) if recorded_argv else ""
        assert "seatbelt-secret-xyz-999" not in full_argv_str

    def test_bubblewrap_env_value_not_in_argv(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as _bm

        monkeypatch.setenv("CROSS_BACKEND_SECRET", "bwrap-secret-xyz-999")

        recorded_argv: list[list[str]] = []

        def record_run(argv, **kwargs):
            recorded_argv.append(list(argv))
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        proposal = _bwrap_proposal(tmp_path, env_keys=["CROSS_BACKEND_SECRET"])
        monkeypatch.setattr(_bm.shutil, "which", lambda name: "/usr/bin/bwrap")
        monkeypatch.setattr(_bm.subprocess, "run", record_run)
        LinuxBubblewrapExecutor(tmp_path, SafeCodeConfig()).execute(proposal)

        full_argv = " ".join(recorded_argv[0]) if recorded_argv else ""
        assert "bwrap-secret-xyz-999" not in full_argv

    def test_docker_env_not_passed_as_env_flag(self, tmp_path, monkeypatch):
        """Docker argv must not contain --env or -e flags for any env var."""
        import safecode.sandbox.docker as _m

        monkeypatch.setenv("SOME_SECRET", "should-not-be-passed")
        recorded_argv: list[list[str]] = []

        def record_run(argv, **kwargs):
            recorded_argv.append(list(argv))
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        proposal = _docker_proposal(tmp_path, env_keys=["SOME_SECRET"])
        monkeypatch.setattr(DockerDaemonChecker, "check", lambda self: (True, ""))
        monkeypatch.setattr(_m.subprocess, "run", record_run)
        DockerExecutor(tmp_path, SafeCodeConfig()).execute(proposal)

        argv = recorded_argv[0] if recorded_argv else []
        assert "--env" not in argv
        assert "-e" not in argv


# ── F. Filesystem boundary: outside-root paths rejected ──────────────────


class TestCrossBackendFilesystemBoundary:
    """Writable paths outside the project root must be rejected by all three
    plan builders — they must not appear in the generated argv, mounts, or
    profile write-allow rules."""

    def test_docker_outside_root_not_in_writable_mounts(self, tmp_path):
        outside = tmp_path.parent / "outside-dir"
        outside.mkdir(exist_ok=True)
        req = _make_request(
            tmp_path, readonly_filesystem=False, writable_paths=[outside]
        )
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert str(outside) not in plan.writable_mounts

    def test_seatbelt_outside_root_not_in_write_paths(self, tmp_path):
        outside = tmp_path.parent / "outside-dir-sb"
        outside.mkdir(exist_ok=True)
        req = _make_request(
            tmp_path, readonly_filesystem=False, writable_paths=[outside]
        )
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert str(outside) not in plan.allowed_write_paths

    def test_bubblewrap_outside_root_not_in_bind_writable(self, tmp_path):
        outside = tmp_path.parent / "outside-dir-bw"
        outside.mkdir(exist_ok=True)
        req = _make_request(
            tmp_path, readonly_filesystem=False, writable_paths=[outside]
        )
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert str(outside) not in plan.bind_writable_paths

    def test_docker_outside_root_not_in_argv(self, tmp_path):
        outside = tmp_path.parent / "outside-argv"
        outside.mkdir(exist_ok=True)
        req = _make_request(
            tmp_path, readonly_filesystem=False, writable_paths=[outside]
        )
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(req)
        # Outside path must not appear as a writable mount arg
        argv_str = " ".join(plan.argv)
        # Check it's not listed as a writable (rw) bind mount
        assert f"src={outside},dst={outside}" not in argv_str

    def test_bubblewrap_outside_root_not_in_argv_as_bind(self, tmp_path):
        outside = tmp_path.parent / "outside-bwrap"
        outside.mkdir(exist_ok=True)
        req = _make_request(
            tmp_path, readonly_filesystem=False, writable_paths=[outside]
        )
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(req)
        argv = plan.argv
        # --bind <outside> <outside> must not appear
        for i in range(len(argv) - 2):
            if argv[i] == "--bind":
                assert argv[i + 1] != str(outside)

    def test_all_three_warn_about_outside_root(self, tmp_path):
        """All three plan builders emit a warning when an outside-root path is given."""
        outside = tmp_path.parent / "outside-warn"
        outside.mkdir(exist_ok=True)
        req = _make_request(
            tmp_path, readonly_filesystem=False, writable_paths=[outside]
        )
        docker_plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(req)
        sb_plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(req)
        bw_plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(req)

        for plan in (docker_plan, sb_plan, bw_plan):
            warn_text = " ".join(plan.warnings).lower()
            assert "outside" in warn_text or "project root" in warn_text


# ── G. Sensitive paths not granted write access ───────────────────────────


class TestCrossBackendSensitivePathRejected:
    """Sensitive path segments (.ssh, .env, .aws, credentials, token, secret)
    must not be granted write access by any plan builder."""

    @pytest.mark.parametrize("sensitive_name", [".ssh", ".env", ".aws", "credentials", "token", "secret"])
    def test_docker_sensitive_not_writable(self, tmp_path, sensitive_name):
        sensitive = tmp_path / sensitive_name
        sensitive.mkdir(exist_ok=True)
        req = _make_request(
            tmp_path, readonly_filesystem=False, writable_paths=[sensitive]
        )
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert str(sensitive) not in plan.writable_mounts

    @pytest.mark.parametrize("sensitive_name", [".ssh", ".env", ".aws", "credentials", "token", "secret"])
    def test_seatbelt_sensitive_not_writable(self, tmp_path, sensitive_name):
        sensitive = tmp_path / sensitive_name
        sensitive.mkdir(exist_ok=True)
        req = _make_request(
            tmp_path, readonly_filesystem=False, writable_paths=[sensitive]
        )
        plan = SeatbeltProfileBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert str(sensitive) not in plan.allowed_write_paths

    @pytest.mark.parametrize("sensitive_name", [".ssh", ".env", ".aws", "credentials", "token", "secret"])
    def test_bubblewrap_sensitive_not_writable(self, tmp_path, sensitive_name):
        sensitive = tmp_path / sensitive_name
        sensitive.mkdir(exist_ok=True)
        req = _make_request(
            tmp_path, readonly_filesystem=False, writable_paths=[sensitive]
        )
        plan = BubblewrapArgsBuilder(tmp_path, SafeCodeConfig()).build(req)
        assert str(sensitive) not in plan.bind_writable_paths


# ── H. Approval claimed atomically before executor invoked ────────────────


class TestCrossBackendGateApprovalFirst:
    """When claim_for_execution returns False, no executor must be invoked.

    This verifies the gate's atomic claim-before-execute ordering for all
    three real backends at the gate integration level.
    """

    def test_docker_executor_not_called_if_claim_fails(self, tmp_path, monkeypatch):
        import safecode.sandbox.docker as _m

        gate, _ = _setup_docker_gate(tmp_path, monkeypatch)
        monkeypatch.setattr(
            SandboxExecutionApprovalStore, "claim_for_execution", lambda *a, **kw: False
        )
        called: list = []
        monkeypatch.setattr(_m.subprocess, "run", lambda *a, **kw: called.append(1))
        result = gate.execute_pending()
        assert result.executed is False
        assert len(called) == 0

    def test_seatbelt_executor_not_called_if_claim_fails(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as _sm

        gate, _ = _setup_seatbelt_gate(tmp_path, monkeypatch)
        monkeypatch.setattr(
            SandboxExecutionApprovalStore, "claim_for_execution", lambda *a, **kw: False
        )
        called: list = []
        monkeypatch.setattr(_sm.subprocess, "run", lambda *a, **kw: called.append(1))
        result = gate.execute_pending()
        assert result.executed is False
        assert len(called) == 0

    def test_bubblewrap_executor_not_called_if_claim_fails(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as _bm

        gate, _ = _setup_bwrap_gate(tmp_path, monkeypatch)
        monkeypatch.setattr(
            SandboxExecutionApprovalStore, "claim_for_execution", lambda *a, **kw: False
        )
        called: list = []
        monkeypatch.setattr(_bm.subprocess, "run", lambda *a, **kw: called.append(1))
        result = gate.execute_pending()
        assert result.executed is False
        assert len(called) == 0

    def test_docker_claim_failure_writes_blocked_result(self, tmp_path, monkeypatch):
        gate, pid = _setup_docker_gate(tmp_path, monkeypatch)
        monkeypatch.setattr(
            SandboxExecutionApprovalStore, "claim_for_execution", lambda *a, **kw: False
        )
        gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(pid)
        assert record is not None
        assert record.status == "blocked_claim"
        assert record.executed is False

    def test_seatbelt_claim_failure_writes_blocked_result(self, tmp_path, monkeypatch):
        gate, pid = _setup_seatbelt_gate(tmp_path, monkeypatch)
        monkeypatch.setattr(
            SandboxExecutionApprovalStore, "claim_for_execution", lambda *a, **kw: False
        )
        gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(pid)
        assert record is not None
        assert record.status == "blocked_claim"

    def test_bubblewrap_claim_failure_writes_blocked_result(self, tmp_path, monkeypatch):
        gate, pid = _setup_bwrap_gate(tmp_path, monkeypatch)
        monkeypatch.setattr(
            SandboxExecutionApprovalStore, "claim_for_execution", lambda *a, **kw: False
        )
        gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(pid)
        assert record is not None
        assert record.status == "blocked_claim"

    def test_docker_claim_failure_clears_pending(self, tmp_path, monkeypatch):
        gate, _ = _setup_docker_gate(tmp_path, monkeypatch)
        monkeypatch.setattr(
            SandboxExecutionApprovalStore, "claim_for_execution", lambda *a, **kw: False
        )
        gate.execute_pending()
        assert not gate.pending_path.exists()

    def test_seatbelt_claim_failure_clears_pending(self, tmp_path, monkeypatch):
        gate, _ = _setup_seatbelt_gate(tmp_path, monkeypatch)
        monkeypatch.setattr(
            SandboxExecutionApprovalStore, "claim_for_execution", lambda *a, **kw: False
        )
        gate.execute_pending()
        assert not gate.pending_path.exists()

    def test_bubblewrap_claim_failure_clears_pending(self, tmp_path, monkeypatch):
        gate, _ = _setup_bwrap_gate(tmp_path, monkeypatch)
        monkeypatch.setattr(
            SandboxExecutionApprovalStore, "claim_for_execution", lambda *a, **kw: False
        )
        gate.execute_pending()
        assert not gate.pending_path.exists()


# ── I. Result record written and pending cleared ──────────────────────────


class TestCrossBackendGateResultLifecycle:
    """For every real backend, a terminal execution attempt (success or
    failure) must write a result record and clear the pending proposal."""

    def test_docker_successful_injection_writes_result(self, tmp_path, monkeypatch):
        gate, pid = _setup_docker_gate(tmp_path, monkeypatch, run_fn=_OK_RUN)
        result = gate.execute_pending()
        assert result.executed is True
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(pid)
        assert record is not None
        assert record.backend == "docker"
        assert record.executed is True
        assert record.status == "completed"

    def test_docker_successful_injection_clears_pending(self, tmp_path, monkeypatch):
        gate, _ = _setup_docker_gate(tmp_path, monkeypatch, run_fn=_OK_RUN)
        gate.execute_pending()
        assert not gate.pending_path.exists()

    def test_seatbelt_successful_injection_writes_result(self, tmp_path, monkeypatch):
        gate, pid = _setup_seatbelt_gate(tmp_path, monkeypatch, run_fn=_OK_RUN)
        result = gate.execute_pending()
        assert result.executed is True
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(pid)
        assert record is not None
        assert record.backend == "macos_seatbelt"
        assert record.executed is True

    def test_seatbelt_successful_injection_clears_pending(self, tmp_path, monkeypatch):
        gate, _ = _setup_seatbelt_gate(tmp_path, monkeypatch, run_fn=_OK_RUN)
        gate.execute_pending()
        assert not gate.pending_path.exists()

    def test_bubblewrap_successful_injection_writes_result(self, tmp_path, monkeypatch):
        gate, pid = _setup_bwrap_gate(tmp_path, monkeypatch, run_fn=_OK_RUN)
        result = gate.execute_pending()
        assert result.executed is True
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(pid)
        assert record is not None
        assert record.backend == "linux_bubblewrap"
        assert record.executed is True

    def test_bubblewrap_successful_injection_clears_pending(self, tmp_path, monkeypatch):
        gate, _ = _setup_bwrap_gate(tmp_path, monkeypatch, run_fn=_OK_RUN)
        gate.execute_pending()
        assert not gate.pending_path.exists()

    def test_docker_blocked_binary_still_writes_result(self, tmp_path, monkeypatch):
        """Docker blocked at executor (daemon unavailable) still writes result."""
        gate, pid = _setup_docker_gate(tmp_path, monkeypatch)
        monkeypatch.setattr(DockerDaemonChecker, "check", lambda self: (False, "daemon down"))
        gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(pid)
        assert record is not None
        assert record.backend == "docker"
        assert record.executed is False

    def test_seatbelt_blocked_binary_still_writes_result(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as _sm
        gate, pid = _setup_seatbelt_gate(tmp_path, monkeypatch)
        monkeypatch.setattr(_sm.shutil, "which", lambda name: None)
        gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(pid)
        assert record is not None
        assert record.executed is False

    def test_bubblewrap_blocked_binary_still_writes_result(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as _bm
        gate, pid = _setup_bwrap_gate(tmp_path, monkeypatch)
        monkeypatch.setattr(_bm.shutil, "which", lambda name: None)
        gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        record = store.load(pid)
        assert record is not None
        assert record.executed is False

    def test_docker_result_record_contains_correct_backend(self, tmp_path, monkeypatch):
        gate, pid = _setup_docker_gate(tmp_path, monkeypatch, run_fn=_OK_RUN)
        gate.execute_pending()
        record = SandboxExecutionResultStore(tmp_path).load(pid)
        assert record.backend == "docker"

    def test_seatbelt_result_record_contains_correct_backend(self, tmp_path, monkeypatch):
        gate, pid = _setup_seatbelt_gate(tmp_path, monkeypatch, run_fn=_OK_RUN)
        gate.execute_pending()
        record = SandboxExecutionResultStore(tmp_path).load(pid)
        assert record.backend == "macos_seatbelt"

    def test_bubblewrap_result_record_contains_correct_backend(self, tmp_path, monkeypatch):
        gate, pid = _setup_bwrap_gate(tmp_path, monkeypatch, run_fn=_OK_RUN)
        gate.execute_pending()
        record = SandboxExecutionResultStore(tmp_path).load(pid)
        assert record.backend == "linux_bubblewrap"


# ── J. Env values not in audit records ───────────────────────────────────


class TestCrossBackendGateEnvNotInAudit:
    """Env values must not appear in any audit record produced by the gate
    for any real backend, even when env_keys are stored in the proposal."""

    def _assert_no_secret_in_events(self, events, secret: str) -> None:
        for event in events:
            combined = str(event.message) + str(event.metadata)
            assert secret not in combined, (
                f"Secret '{secret}' leaked into audit event {event.type!r}"
            )

    def test_docker_env_not_in_audit(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DOCKER_AUDIT_SECRET", "docker-audit-secret-xyz")
        gate = _setup_base_gate(tmp_path, monkeypatch)
        docker_cap = SandboxCapability(
            backend=SandboxBackend.DOCKER, available=True, supported_platforms=["all"], reason="test"
        )
        adapter = DockerSandboxAdapter(docker_cap, project_root=tmp_path, config=SafeCodeConfig())
        req = _make_request(tmp_path, env={"DOCKER_AUDIT_SECRET": "docker-audit-secret-xyz"})
        plan = adapter.build_plan(req)
        gate.propose(plan, "test")
        gate.approve()
        _mock_backend_available(monkeypatch, SandboxBackend.DOCKER)
        monkeypatch.setattr(DockerDaemonChecker, "check", lambda self: (True, ""))
        import safecode.sandbox.docker as _m
        monkeypatch.setattr(_m.subprocess, "run", _OK_RUN)
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=20)
        self._assert_no_secret_in_events(events, "docker-audit-secret-xyz")

    def test_seatbelt_env_not_in_audit(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SEATBELT_AUDIT_SECRET", "seatbelt-audit-secret-xyz")
        gate = _setup_base_gate(tmp_path, monkeypatch)
        seatbelt_cap = SandboxCapability(
            backend=SandboxBackend.MACOS_SEATBELT, available=True, supported_platforms=["darwin"], reason="test"
        )
        adapter = MacOSSeatbeltAdapter(seatbelt_cap, project_root=tmp_path, config=SafeCodeConfig())
        req = _make_request(tmp_path, env={"SEATBELT_AUDIT_SECRET": "seatbelt-audit-secret-xyz"})
        plan = adapter.build_plan(req)
        gate.propose(plan, "test")
        gate.approve()
        _mock_backend_available(monkeypatch, SandboxBackend.MACOS_SEATBELT)
        import safecode.sandbox.seatbelt as _sm
        monkeypatch.setattr(_sm.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        monkeypatch.setattr(_sm.subprocess, "run", _OK_RUN)
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=20)
        self._assert_no_secret_in_events(events, "seatbelt-audit-secret-xyz")

    def test_bubblewrap_env_not_in_audit(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BWRAP_AUDIT_SECRET", "bwrap-audit-secret-xyz")
        gate = _setup_base_gate(tmp_path, monkeypatch)
        bwrap_cap = SandboxCapability(
            backend=SandboxBackend.LINUX_BUBBLEWRAP, available=True, supported_platforms=["linux"], reason="test"
        )
        adapter = LinuxBubblewrapAdapter(bwrap_cap, project_root=tmp_path, config=SafeCodeConfig())
        req = _make_request(tmp_path, env={"BWRAP_AUDIT_SECRET": "bwrap-audit-secret-xyz"})
        plan = adapter.build_plan(req)
        gate.propose(plan, "test")
        gate.approve()
        _mock_backend_available(monkeypatch, SandboxBackend.LINUX_BUBBLEWRAP)
        import safecode.sandbox.bubblewrap as _bm
        monkeypatch.setattr(_bm.shutil, "which", lambda name: "/usr/bin/bwrap")
        monkeypatch.setattr(_bm.subprocess, "run", _OK_RUN)
        gate.execute_pending()
        events = AuditLogger(tmp_path).read_recent(limit=20)
        self._assert_no_secret_in_events(events, "bwrap-audit-secret-xyz")

    def test_docker_env_not_in_result_record(self, tmp_path, monkeypatch):
        """Env values must not appear in the persisted result record JSON."""
        import json as _json

        monkeypatch.setenv("DOCKER_RESULT_SECRET", "docker-result-secret-xyz")
        gate, pid = _setup_docker_gate(tmp_path, monkeypatch, run_fn=_OK_RUN)
        gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        record_path = store._path_for(pid)
        raw = record_path.read_text(encoding="utf-8")
        assert "docker-result-secret-xyz" not in raw

    def test_seatbelt_env_not_in_result_record(self, tmp_path, monkeypatch):
        import json as _json

        monkeypatch.setenv("SEATBELT_RESULT_SECRET", "seatbelt-result-secret-xyz")
        gate, pid = _setup_seatbelt_gate(tmp_path, monkeypatch, run_fn=_OK_RUN)
        gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        record_path = store._path_for(pid)
        raw = record_path.read_text(encoding="utf-8")
        assert "seatbelt-result-secret-xyz" not in raw

    def test_bubblewrap_env_not_in_result_record(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BWRAP_RESULT_SECRET", "bwrap-result-secret-xyz")
        gate, pid = _setup_bwrap_gate(tmp_path, monkeypatch, run_fn=_OK_RUN)
        gate.execute_pending()
        store = SandboxExecutionResultStore(tmp_path)
        record_path = store._path_for(pid)
        raw = record_path.read_text(encoding="utf-8")
        assert "bwrap-result-secret-xyz" not in raw


# ── K. Preflight must pass before execution reaches any executor ──────────


class TestCrossBackendPreflightRequired:
    """All four checks — approval, command policy, backend availability, and
    filesystem boundary — must pass before any executor is invoked."""

    def test_docker_no_approval_blocks_before_executor(self, tmp_path, monkeypatch):
        import safecode.sandbox.docker as _m

        gate = _setup_base_gate(tmp_path, monkeypatch)
        docker_cap = SandboxCapability(
            backend=SandboxBackend.DOCKER, available=True, supported_platforms=["all"], reason="test"
        )
        adapter = DockerSandboxAdapter(docker_cap, project_root=tmp_path, config=SafeCodeConfig())
        plan = adapter.build_plan(_make_request(tmp_path))
        gate.propose(plan, "test")
        # no gate.approve()
        _mock_backend_available(monkeypatch, SandboxBackend.DOCKER)
        called: list = []
        monkeypatch.setattr(_m.subprocess, "run", lambda *a, **kw: called.append(1))
        result = gate.execute_pending()
        assert result.executed is False
        assert len(called) == 0

    def test_seatbelt_no_approval_blocks_before_executor(self, tmp_path, monkeypatch):
        import safecode.sandbox.seatbelt as _sm

        gate = _setup_base_gate(tmp_path, monkeypatch)
        seatbelt_cap = SandboxCapability(
            backend=SandboxBackend.MACOS_SEATBELT, available=True, supported_platforms=["darwin"], reason="test"
        )
        adapter = MacOSSeatbeltAdapter(seatbelt_cap, project_root=tmp_path, config=SafeCodeConfig())
        plan = adapter.build_plan(_make_request(tmp_path))
        gate.propose(plan, "test")
        _mock_backend_available(monkeypatch, SandboxBackend.MACOS_SEATBELT)
        monkeypatch.setattr(_sm.shutil, "which", lambda name: "/usr/bin/sandbox-exec")
        called: list = []
        monkeypatch.setattr(_sm.subprocess, "run", lambda *a, **kw: called.append(1))
        result = gate.execute_pending()
        assert result.executed is False
        assert len(called) == 0

    def test_bubblewrap_no_approval_blocks_before_executor(self, tmp_path, monkeypatch):
        import safecode.sandbox.bubblewrap as _bm

        gate = _setup_base_gate(tmp_path, monkeypatch)
        bwrap_cap = SandboxCapability(
            backend=SandboxBackend.LINUX_BUBBLEWRAP, available=True, supported_platforms=["linux"], reason="test"
        )
        adapter = LinuxBubblewrapAdapter(bwrap_cap, project_root=tmp_path, config=SafeCodeConfig())
        plan = adapter.build_plan(_make_request(tmp_path))
        gate.propose(plan, "test")
        _mock_backend_available(monkeypatch, SandboxBackend.LINUX_BUBBLEWRAP)
        monkeypatch.setattr(_bm.shutil, "which", lambda name: "/usr/bin/bwrap")
        called: list = []
        monkeypatch.setattr(_bm.subprocess, "run", lambda *a, **kw: called.append(1))
        result = gate.execute_pending()
        assert result.executed is False
        assert len(called) == 0

    def test_all_backends_write_audit_on_successful_execution(self, tmp_path, monkeypatch):
        """Each backend must write a sandbox_execution_completed audit event."""
        for setup_fn in [_setup_docker_gate, _setup_seatbelt_gate, _setup_bwrap_gate]:
            gate, pid = setup_fn(tmp_path, monkeypatch, run_fn=_OK_RUN)
            gate.execute_pending()
            events = AuditLogger(tmp_path).read_recent(limit=30)
            types = [e.type for e in events]
            assert "sandbox_execution_completed" in types, (
                f"Expected sandbox_execution_completed for {setup_fn.__name__}"
            )
            assert "sandbox_execution_approval_claimed" in types
            # clean up pending and approval state for next iteration
            gate.store.discard_pending()
