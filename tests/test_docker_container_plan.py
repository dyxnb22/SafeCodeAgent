"""Docker container plan tests for v1.7.3.

Verifies DockerContainerPlanBuilder generates conservative docker run
arguments without executing docker.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.sandbox.adapter import (
    DockerSandboxAdapter,
    LinuxBubblewrapAdapter,
    MacOSSeatbeltAdapter,
    NoopSandboxAdapter,
    SandboxExecutionRequest,
)
from safecode.sandbox.capabilities import SandboxBackend, SandboxCapability
from safecode.sandbox.docker import DEFAULT_IMAGE, DockerContainerPlanBuilder, DockerContainerPlan


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
        assert any("v1.7.3" in w for w in plan.warnings)

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
