"""Docker container plan and execution tests for v2.4.0.

Verifies DockerContainerPlanBuilder generates conservative docker run
arguments, DockerDaemonChecker detects daemon availability, and
DockerExecutor runs proposals without requiring a real Docker daemon.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import (
    DockerSandboxAdapter,
    LinuxBubblewrapAdapter,
    MacOSSeatbeltAdapter,
    NoopSandboxAdapter,
    SandboxExecutionRequest,
)
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability
from safecode.sandbox.docker import (
    DEFAULT_IMAGE,
    DockerContainerPlan,
    DockerContainerPlanBuilder,
    DockerDaemonChecker,
    DockerExecutionResult,
    DockerExecutor,
)


def _make_request(**kwargs):
    defaults = {
        "command": ["echo", "hello"],
        "cwd": Path("/tmp/test_project"),
        "purpose": "shell",
        "allow_network": False,
        "readonly_filesystem": True,
        "writable_paths": [],
        "env": {},
        "timeout_seconds": 30,
    }
    defaults.update(kwargs)
    return SandboxExecutionRequest(**defaults)


def _make_docker_cap():
    return SandboxCapability(
        backend=SandboxBackend.DOCKER,
        available=True,
        supported_platforms=["all"],
        reason="test",
        limitations=["test limitation"],
    )


# ── DockerContainerPlanBuilder tests ───────────────────────────────────


class TestDockerContainerPlanBuilder:
    def test_argv_starts_with_docker_run(self, tmp_path):
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert plan.argv[0] == "docker"
        assert plan.argv[1] == "run"

    def test_includes_rm_and_init(self, tmp_path):
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert "--rm" in plan.argv
        assert "--init" in plan.argv

    def test_workdir_set_to_project_root(self, tmp_path):
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert "--workdir" in plan.argv
        idx = plan.argv.index("--workdir")
        assert plan.argv[idx + 1] == str(tmp_path)

    def test_network_disabled_includes_network_none(self, tmp_path):
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(allow_network=False)
        )
        assert "--network" in plan.argv
        assert "none" in plan.argv

    def test_network_enabled_no_network_none_with_warning(self, tmp_path):
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(allow_network=True)
        )
        args_str = " ".join(plan.argv)
        assert "--network none" not in args_str
        assert any("require approval" in w for w in plan.warnings)

    def test_readonly_filesystem_includes_read_only(self, tmp_path):
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=True)
        )
        assert "--read-only" in plan.argv

    def test_readonly_filesystem_false_no_read_only(self, tmp_path):
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=False)
        )
        assert "--read-only" not in plan.argv

    def test_project_root_readonly_mount(self, tmp_path):
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert str(tmp_path) in plan.readonly_mounts
        assert "readonly" in " ".join(plan.argv)

    def test_writable_inside_project_allows_mount(self, tmp_path):
        writable = tmp_path / "output"
        writable.mkdir()
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=False, writable_paths=[writable])
        )
        assert str(writable) in plan.writable_mounts

    def test_writable_outside_project_rejected(self, tmp_path):
        outside = tmp_path.parent / "outside_dir"
        outside.mkdir(exist_ok=True)
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=False, writable_paths=[outside])
        )
        assert str(outside) not in plan.writable_mounts

    def test_sensitive_writable_path_not_in_mounts(self, tmp_path):
        sensitive_file = tmp_path / "secret.pem"
        sensitive_file.write_text("private", encoding="utf-8")
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=False, writable_paths=[sensitive_file])
        )
        assert str(sensitive_file) not in plan.writable_mounts

    def test_writable_path_with_comma_not_mounted(self, tmp_path):
        unsafe = tmp_path / "unsafe,path"
        unsafe.mkdir()
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(readonly_filesystem=False, writable_paths=[unsafe])
        )
        assert str(unsafe) not in plan.writable_mounts
        assert any("unsafe for Docker --mount" in warning for warning in plan.warnings)

    def test_blocked_writable_roots_not_mounted(self, tmp_path):
        for blocked in ["/home", "/tmp", "/var", "/private", "/root"]:
            bp = Path(blocked) / "sub"
            builder = DockerContainerPlanBuilder(Path("/tmp/test_project"), SafeCodeConfig())
            plan = builder.build(
                _make_request(readonly_filesystem=False, writable_paths=[bp])
            )
            assert str(bp) not in plan.writable_mounts

    def test_tmpfs_with_security_options(self, tmp_path):
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert "/tmp:rw,noexec,nosuid,nodev" in plan.tmpfs_mounts
        assert "--tmpfs" in plan.argv

    def test_image_before_command(self, tmp_path):
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(_make_request())
        assert DEFAULT_IMAGE in plan.argv
        img_idx = plan.argv.index(DEFAULT_IMAGE)
        assert plan.argv[img_idx + 1 :] == ["echo", "hello"]

    def test_command_appended_at_end(self, tmp_path):
        command = ["python", "-c", "print(1)"]
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(command=command)
        )
        img_idx = plan.argv.index(DEFAULT_IMAGE)
        assert plan.argv[img_idx + 1 :] == command

    def test_env_values_not_in_argv(self, tmp_path):
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(
            _make_request(env={"API_KEY": "supersecret", "HOME": "/home"})
        )
        assert "supersecret" not in " ".join(plan.argv)
        assert "supersecret" not in " ".join(plan.warnings)


# ── adapter integration tests ─────────────────────────────────────────


class TestAdapterContainerIntegration:
    def test_docker_adapter_fills_container_preview(self, tmp_path):
        cap = _make_docker_cap()
        adapter = DockerSandboxAdapter(cap, project_root=tmp_path, config=SafeCodeConfig())
        plan = adapter.build_plan(_make_request(cwd=tmp_path))
        assert len(plan.container_preview) > 0
        assert plan.container_backend == "docker"
        assert plan.container_preview[0] == "docker"
        assert plan.container_preview[1] == "run"

    def test_docker_adapter_respects_config_network_disabled(self, tmp_path):
        cap = _make_docker_cap()
        config = SafeCodeConfig()
        config.sandbox.network_enabled = False
        adapter = DockerSandboxAdapter(cap, project_root=tmp_path, config=config)

        plan = adapter.build_plan(_make_request(cwd=tmp_path, allow_network=True))

        assert plan.network_enabled is False
        assert "--network" in plan.container_preview
        assert "none" in plan.container_preview
        assert any("Network access was requested" in warning for warning in plan.warnings)

    def test_noop_adapter_no_container_preview(self):
        plan = NoopSandboxAdapter().build_plan(_make_request())
        assert len(plan.container_preview) == 0
        assert plan.container_backend is None

    def test_macos_adapter_no_container_preview(self, tmp_path):
        cap = SandboxCapability(
            backend=SandboxBackend.MACOS_SEATBELT,
            available=True,
            supported_platforms=["macOS"],
            reason="test",
        )
        adapter = MacOSSeatbeltAdapter(cap, project_root=tmp_path, config=SafeCodeConfig())
        plan = adapter.build_plan(_make_request(cwd=tmp_path))
        assert len(plan.container_preview) == 0

    def test_linux_adapter_no_container_preview(self, tmp_path):
        cap = SandboxCapability(
            backend=SandboxBackend.LINUX_BUBBLEWRAP,
            available=True,
            supported_platforms=["Linux"],
            reason="test",
        )
        adapter = LinuxBubblewrapAdapter(cap, project_root=tmp_path, config=SafeCodeConfig())
        plan = adapter.build_plan(_make_request(cwd=tmp_path))
        assert len(plan.container_preview) == 0

    def test_adapter_no_subprocess(self, tmp_path, monkeypatch):
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "call", lambda *a, **kw: called.append(1))
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: called.append(1))

        cap = _make_docker_cap()
        DockerSandboxAdapter(cap, project_root=tmp_path, config=SafeCodeConfig()).build_plan(
            _make_request(cwd=tmp_path)
        )
        assert len(called) == 0


# ── v2.4.0: DockerDaemonChecker tests ────────────────────────────────


def _make_fake_proc(returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=b"", stderr=b"")


class TestDockerDaemonChecker:
    def test_daemon_available_returncode_zero(self):
        checker = DockerDaemonChecker(run_fn=lambda *a, **kw: _make_fake_proc(0))
        available, reason = checker.check()
        assert available is True
        assert reason == ""

    def test_daemon_unavailable_nonzero_returncode(self):
        checker = DockerDaemonChecker(run_fn=lambda *a, **kw: _make_fake_proc(1))
        available, reason = checker.check()
        assert available is False
        assert "exit 1" in reason

    def test_docker_cli_not_found(self):
        def raise_fnf(*a, **kw):
            raise FileNotFoundError("docker not found")

        checker = DockerDaemonChecker(run_fn=raise_fnf)
        available, reason = checker.check()
        assert available is False
        assert "not found" in reason.lower()

    def test_timeout_returns_unavailable(self):
        def raise_timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="docker", timeout=5)

        checker = DockerDaemonChecker(run_fn=raise_timeout)
        available, reason = checker.check()
        assert available is False
        assert "5s" in reason

    def test_oserror_returns_unavailable(self):
        def raise_os(*a, **kw):
            raise OSError("permission denied")

        checker = DockerDaemonChecker(run_fn=raise_os)
        available, reason = checker.check()
        assert available is False
        assert "permission denied" in reason.lower()

    def test_info_argv_is_list_no_shell(self):
        """Daemon check must use a token list (no shell=True)."""
        calls = []

        def capture(*a, **kw):
            calls.append({"args": a, "kwargs": kw})
            return _make_fake_proc(0)

        DockerDaemonChecker(run_fn=capture).check()
        assert len(calls) == 1
        kw = calls[0]["kwargs"]
        assert kw.get("shell") is False
        assert isinstance(calls[0]["args"][0], list)

    def test_never_raises(self):
        """check() must never propagate exceptions."""
        for exc in [RuntimeError("boom"), ValueError("bad")]:
            def raise_it(*a, **kw):
                raise exc

            checker = DockerDaemonChecker(run_fn=raise_it)
            available, reason = checker.check()
            assert available is False
            assert reason


# ── v2.4.0: DockerExecutor tests ─────────────────────────────────────


def _make_proposal_ns(
    command=None,
    cwd="/tmp/test_project",
    network_enabled=False,
    readonly_filesystem=True,
    writable_paths=None,
    preview_hash=None,
    backend="docker",
):
    """Build a SimpleNamespace that looks like SandboxExecutionProposal."""
    return SimpleNamespace(
        proposal_id="test-proposal-id",
        command=command or ["echo", "hello"],
        cwd=cwd,
        purpose="shell",
        network_enabled=network_enabled,
        readonly_filesystem=readonly_filesystem,
        writable_paths=writable_paths or [],
        env_keys=[],
        preview_hash=preview_hash,
        backend=backend,
    )


def _stable_hash(argv: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(argv, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class TestDockerExecutor:
    def _make_executor(self, tmp_path, daemon_ok=True, proc_returncode=0, proc_stdout=b"", proc_stderr=b""):
        def fake_daemon_run(*a, **kw):
            return _make_fake_proc(0 if daemon_ok else 1)

        def fake_docker_run(argv, **kw):
            return SimpleNamespace(returncode=proc_returncode, stdout=proc_stdout, stderr=proc_stderr)

        return DockerExecutor(
            project_root=tmp_path,
            config=SafeCodeConfig(),
            daemon_checker=DockerDaemonChecker(run_fn=fake_daemon_run),
            run_fn=fake_docker_run,
        )

    def test_successful_execution_returns_executed_true(self, tmp_path):
        executor = self._make_executor(tmp_path, daemon_ok=True, proc_stdout=b"hello\n")
        proposal = _make_proposal_ns(cwd=str(tmp_path))
        plan = DockerContainerPlanBuilder(tmp_path, SafeCodeConfig()).build(
            SandboxExecutionRequest(
                command=proposal.command,
                cwd=tmp_path,
                purpose="shell",
                allow_network=proposal.network_enabled,
                readonly_filesystem=proposal.readonly_filesystem,
                writable_paths=[],
                env={},
                timeout_seconds=30,
            )
        )
        proposal.preview_hash = _stable_hash(plan.argv)
        result = executor.execute(proposal)
        assert result.executed is True
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_daemon_unavailable_returns_executed_false(self, tmp_path):
        executor = self._make_executor(tmp_path, daemon_ok=False)
        proposal = _make_proposal_ns(cwd=str(tmp_path))
        result = executor.execute(proposal)
        assert result.executed is False
        assert "unavailable" in result.message.lower()

    def test_hash_mismatch_returns_executed_false(self, tmp_path):
        executor = self._make_executor(tmp_path, daemon_ok=True)
        proposal = _make_proposal_ns(cwd=str(tmp_path), preview_hash="wrong" * 16)
        result = executor.execute(proposal)
        assert result.executed is False
        assert "hash mismatch" in result.message.lower()

    def test_timeout_returns_executed_false(self, tmp_path):
        def raise_timeout(argv, **kw):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=30)

        def fake_daemon_run(*a, **kw):
            return _make_fake_proc(0)

        executor = DockerExecutor(
            project_root=tmp_path,
            config=SafeCodeConfig(),
            daemon_checker=DockerDaemonChecker(run_fn=fake_daemon_run),
            run_fn=raise_timeout,
        )
        proposal = _make_proposal_ns(cwd=str(tmp_path))
        result = executor.execute(proposal)
        assert result.executed is False
        assert "timed out" in result.message.lower()

    def test_oserror_returns_executed_false(self, tmp_path):
        def raise_os(argv, **kw):
            raise OSError("docker run failed")

        def fake_daemon_run(*a, **kw):
            return _make_fake_proc(0)

        executor = DockerExecutor(
            project_root=tmp_path,
            config=SafeCodeConfig(),
            daemon_checker=DockerDaemonChecker(run_fn=fake_daemon_run),
            run_fn=raise_os,
        )
        proposal = _make_proposal_ns(cwd=str(tmp_path))
        result = executor.execute(proposal)
        assert result.executed is False
        assert "docker run failed" in result.message.lower()

    def test_no_shell_true_in_run_call(self, tmp_path):
        """Docker execution must not use shell=True."""
        run_calls = []

        def capture_run(argv, **kw):
            run_calls.append(kw)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        def fake_daemon_run(*a, **kw):
            return _make_fake_proc(0)

        executor = DockerExecutor(
            project_root=tmp_path,
            config=SafeCodeConfig(),
            daemon_checker=DockerDaemonChecker(run_fn=fake_daemon_run),
            run_fn=capture_run,
        )
        proposal = _make_proposal_ns(cwd=str(tmp_path))
        executor.execute(proposal)
        assert len(run_calls) == 1
        assert run_calls[0].get("shell") is False

    def test_network_disabled_in_docker_argv(self, tmp_path):
        """When network_enabled=False, docker argv must contain --network none."""
        run_calls = []

        def capture_run(argv, **kw):
            run_calls.append(argv)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        def fake_daemon_run(*a, **kw):
            return _make_fake_proc(0)

        executor = DockerExecutor(
            project_root=tmp_path,
            config=SafeCodeConfig(),
            daemon_checker=DockerDaemonChecker(run_fn=fake_daemon_run),
            run_fn=capture_run,
        )
        proposal = _make_proposal_ns(cwd=str(tmp_path), network_enabled=False)
        executor.execute(proposal)
        assert len(run_calls) == 1
        argv = run_calls[0]
        assert "--network" in argv
        idx = argv.index("--network")
        assert argv[idx + 1] == "none"

    def test_privileged_not_in_docker_argv(self, tmp_path):
        """Docker execution must never pass --privileged."""
        run_calls = []

        def capture_run(argv, **kw):
            run_calls.append(argv)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        def fake_daemon_run(*a, **kw):
            return _make_fake_proc(0)

        executor = DockerExecutor(
            project_root=tmp_path,
            config=SafeCodeConfig(),
            daemon_checker=DockerDaemonChecker(run_fn=fake_daemon_run),
            run_fn=capture_run,
        )
        executor.execute(_make_proposal_ns(cwd=str(tmp_path)))
        assert "--privileged" not in run_calls[0]

    def test_project_root_mounted_readonly(self, tmp_path):
        """Project root must appear as a read-only bind mount."""
        run_calls = []

        def capture_run(argv, **kw):
            run_calls.append(argv)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        def fake_daemon_run(*a, **kw):
            return _make_fake_proc(0)

        executor = DockerExecutor(
            project_root=tmp_path,
            config=SafeCodeConfig(),
            daemon_checker=DockerDaemonChecker(run_fn=fake_daemon_run),
            run_fn=capture_run,
        )
        executor.execute(_make_proposal_ns(cwd=str(tmp_path)))
        argv = run_calls[0]
        argv_str = " ".join(argv)
        assert "readonly" in argv_str
        assert str(tmp_path) in argv_str

    def test_no_env_values_in_docker_argv(self, tmp_path):
        """Environment variable values must not appear in docker run argv."""
        run_calls = []

        def capture_run(argv, **kw):
            run_calls.append(argv)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        def fake_daemon_run(*a, **kw):
            return _make_fake_proc(0)

        executor = DockerExecutor(
            project_root=tmp_path,
            config=SafeCodeConfig(),
            daemon_checker=DockerDaemonChecker(run_fn=fake_daemon_run),
            run_fn=capture_run,
        )
        proposal = _make_proposal_ns(cwd=str(tmp_path))
        proposal = SimpleNamespace(**{**vars(proposal), "env_keys": ["SECRET"]})
        executor.execute(proposal)
        argv_str = " ".join(run_calls[0])
        assert "SECRET" not in argv_str

    def test_non_zero_exit_executed_true(self, tmp_path):
        """Non-zero container exit still counts as executed (not blocked)."""
        executor = self._make_executor(tmp_path, daemon_ok=True, proc_returncode=1)
        proposal = _make_proposal_ns(cwd=str(tmp_path))
        result = executor.execute(proposal)
        assert result.executed is True
        assert result.exit_code == 1

    def test_duration_ms_set(self, tmp_path):
        """duration_ms must be a non-negative integer."""
        executor = self._make_executor(tmp_path, daemon_ok=True)
        result = executor.execute(_make_proposal_ns(cwd=str(tmp_path)))
        assert isinstance(result.duration_ms, int)
        assert result.duration_ms >= 0

    def test_null_preview_hash_skips_integrity_check(self, tmp_path):
        """When preview_hash is None the integrity check is skipped."""
        executor = self._make_executor(tmp_path, daemon_ok=True)
        proposal = _make_proposal_ns(cwd=str(tmp_path), preview_hash=None)
        result = executor.execute(proposal)
        assert result.executed is True


# ── v2.4.0: DockerSandboxAdapter.supports_execution ───────────────────


class TestDockerAdapterSupportsExecution:
    def test_docker_adapter_supports_execution_true(self):
        """v2.4.0: DockerSandboxAdapter now supports execution."""
        cap = _make_docker_cap()
        assert DockerSandboxAdapter(cap).supports_execution() is True

    def test_macos_adapter_supports_execution_v241(self):
        """v2.4.1: MacOSSeatbeltAdapter now supports execution."""
        cap = SandboxCapability(
            backend=SandboxBackend.MACOS_SEATBELT,
            available=True,
            supported_platforms=["macOS"],
            reason="test",
        )
        assert MacOSSeatbeltAdapter(cap).supports_execution() is True

    def test_linux_adapter_supports_execution_in_v242(self):
        """v2.4.2: Linux Bubblewrap now supports real execution."""
        cap = SandboxCapability(
            backend=SandboxBackend.LINUX_BUBBLEWRAP,
            available=True,
            supported_platforms=["Linux"],
            reason="test",
        )
        assert LinuxBubblewrapAdapter(cap).supports_execution() is True

    def test_noop_adapter_supports_execution(self):
        assert NoopSandboxAdapter().supports_execution() is True


# ── regression tests ──────────────────────────────────────────────────


class TestExistingSuiteRegression:
    def test_sandbox_plan_works(self, tmp_path):
        from safecode.sandbox.factory import SandboxAdapterFactory
        plan = SandboxAdapterFactory(tmp_path).create_plan(["echo", "hello"])
        assert plan.dry_run is True

    def test_mcp_readonly_still_works(self, tmp_path, monkeypatch):
        from safecode.mcp.runner import MCPReadOnlyRunner
        anchor_dir = tmp_path.parent / f"anchors-{tmp_path.name}"
        monkeypatch.setenv("SAFECODE_AUDIT_ANCHOR_DIR", str(anchor_dir))
        server_path = tmp_path / "mock_server.py"
        server_path.write_text(
            "import json,sys\np=json.loads(sys.stdin.read() or '{}')\nprint(json.dumps({'output':{'ok':True}}))",
            encoding="utf-8",
        )
        (tmp_path / ".sac").mkdir()
        (tmp_path / ".sac" / "mcp.toml").write_text(
            f'[servers.mock]\ncommand = "{shlex.join([sys.executable, str(server_path)])}"\nenabled = true\n',
            encoding="utf-8",
        )
        config = SafeCodeConfig()
        config.shell.allowed_commands = [sys.executable]
        config.shell.require_confirm_for_medium = False
        config.sandbox.network_enabled = True
        result = MCPReadOnlyRunner(tmp_path, config).call_readonly("mock", "mock.list", {})
        assert result.blocked is False
