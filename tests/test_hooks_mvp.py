"""Tests for deterministic hook stages (v6.1.x portfolio polish)."""

from pathlib import Path
from unittest.mock import patch

from safecode.agent.command_tool import _run_command_handler
from safecode.audit.models import AuditEvent
from safecode.config import SafeCodeConfig
from safecode.hooks.approvals import HookApprovalStore
from safecode.hooks.runner import HookRunner, is_test_command
from safecode.shell.risk import RiskLevel, ShellRisk
from safecode.shell.runner import ShellRunResult


def _ok(command: str = "echo hook") -> ShellRunResult:
    return ShellRunResult(
        command=command,
        risk=ShellRisk(level=RiskLevel.LOW, reasons=[], tokens=command.split()),
        exit_code=0,
        stdout="ok\n",
        stderr="",
        duration_ms=1,
        executed=True,
    )


def _config(stage: str, command: str = "git status") -> SafeCodeConfig:
    cfg = SafeCodeConfig()
    setattr(cfg.hooks, stage, [command])
    cfg.hooks.allow_medium_after_apply = True
    cfg.shell.allowed_commands = ["git", "echo", "pytest"]
    return cfg


def _events(project_root: Path, cfg: SafeCodeConfig, stage: str) -> list[AuditEvent]:
    runner = HookRunner(project_root, cfg)
    written: list[AuditEvent] = []
    runner.audit_logger.write = written.append  # type: ignore[method-assign]
    with patch("safecode.hooks.runner.ShellRunner.run", return_value=_ok()):
        runner.run_stage(stage)
    return written


def test_new_hook_stages_run_with_stage_metadata(tmp_path: Path) -> None:
    for stage in ("before_command", "after_edit", "after_test"):
        cfg = _config(stage)
        HookApprovalStore(tmp_path, cfg).approve(stage, "git status")
        events = _events(tmp_path, cfg, stage)
        assert "hook_completed" in [event.type for event in events]
        assert all(event.metadata.get("hook") == stage for event in events)


def test_unknown_hook_stage_fails_closed(tmp_path: Path) -> None:
    cfg = SafeCodeConfig()
    try:
        HookRunner(tmp_path, cfg).run_stage("after_everything")
    except ValueError as exc:
        assert "unknown hook stage" in str(exc)
    else:
        raise AssertionError("unknown hook stage should fail closed")


def test_hook_approval_hash_includes_stage(tmp_path: Path) -> None:
    cfg = _config("before_command")
    store = HookApprovalStore(tmp_path, cfg)
    assert store.command_hash("before_command", "git status") != store.command_hash(
        "after_test", "git status"
    )


def test_is_test_command_detects_common_test_commands() -> None:
    assert is_test_command("pytest -q")
    assert is_test_command("python -m pytest tests/")
    assert is_test_command("npm test")
    assert is_test_command("go test ./...")
    assert not is_test_command("git status")


def test_native_run_command_triggers_before_and_after_test_hooks(tmp_path: Path) -> None:
    cfg = SafeCodeConfig()
    cfg.hooks.before_command = ["echo before"]
    cfg.hooks.after_test = ["echo after"]
    (tmp_path / ".sac").mkdir()
    (tmp_path / ".sac" / "config.toml").write_text(cfg.to_toml(), encoding="utf-8")

    result = _run_command_handler(
        "call-1",
        {"_project_root": str(tmp_path), "command": "echo pytest", "timeout_seconds": 5},
    )

    assert result.status == "success"
    events = [event.type for event in HookRunner(tmp_path, cfg).audit_logger.read_recent(limit=20)]
    assert events.count("hook_proposed") >= 2
    assert events.count("hook_skipped_by_policy") >= 2
