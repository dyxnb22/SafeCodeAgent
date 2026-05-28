from pathlib import Path

from safecode.config import SafeCodeConfig, merge_trusted_config
from safecode.checkpoint.manager import CheckpointManager
from safecode.context.collector import ContextCollector
from safecode.hooks.runner import HookRunner
from safecode.llm.factory import create_llm_client
from safecode.llm.mock import MockLLMClient
from safecode.mcp.discovery import MCPDiscovery
from safecode.patch.models import PatchBlock, PatchProposal
from safecode.patch.validator import PatchValidationError, PatchValidator
from safecode.shell.risk import RiskLevel, ShellRiskClassifier
from safecode.shell.runner import ShellRunner


def test_high_risk_command_is_blocked_even_when_approved(tmp_path: Path) -> None:
    result = ShellRunner(tmp_path).run("rm -rf /tmp/safecode-example", approved=True)

    assert result.executed is False
    assert result.exit_code == 126


def test_shell_operator_is_high_risk(tmp_path: Path) -> None:
    risk = ShellRiskClassifier().classify("echo hello && rm -rf /tmp/example")

    assert risk.level == RiskLevel.HIGH
    assert any("shell operator" in reason for reason in risk.reasons)


def test_shell_runner_uses_argv_execution(tmp_path: Path) -> None:
    result = ShellRunner(tmp_path).run("echo hello", approved=False)

    assert result.executed is True
    assert result.stdout.strip() == "hello"


def test_project_config_cannot_lower_user_security() -> None:
    user = SafeCodeConfig(policy="strict")
    project = SafeCodeConfig(policy="learning")
    project.shell.block_high_risk = False
    project.shell.require_confirm_for_medium = False
    project.sandbox.network_enabled = True

    merged = merge_trusted_config(user, project)

    assert merged.policy == "strict"
    assert merged.shell.block_high_risk is True
    assert merged.shell.require_confirm_for_medium is True
    assert merged.sandbox.network_enabled is False


def test_patch_validator_uses_sandbox_boundary(tmp_path: Path) -> None:
    proposal = PatchProposal(
        id="patch-test",
        task="escape",
        blocks=[PatchBlock(operation="update", file_path=Path("../outside.txt"), search="a", replace="b")],
        created_at="2026-01-01T00:00:00Z",
        model="test",
    )

    try:
        PatchValidator(tmp_path).validate(proposal)
    except PatchValidationError as exc:
        assert "escapes project root" in str(exc)
    else:
        raise AssertionError("Path escape should be rejected.")


def test_mcp_write_operations_are_disabled(tmp_path: Path) -> None:
    try:
        MCPDiscovery(tmp_path).assert_write_allowed()
    except PermissionError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("MCP writes should be rejected by default.")


def test_llm_factory_defaults_to_mock() -> None:
    client = create_llm_client(SafeCodeConfig())

    assert isinstance(client, MockLLMClient)


def test_hook_injection_is_blocked_by_shell_policy(tmp_path: Path) -> None:
    config = SafeCodeConfig()
    config.hooks.after_apply = ["rm -rf /tmp/safecode-hook-example"]

    summary = HookRunner(tmp_path, config).run_after_apply()

    assert summary.results[0].executed is False
    assert summary.results[0].exit_code == 126


def test_medium_risk_hook_is_not_auto_approved(tmp_path: Path) -> None:
    config = SafeCodeConfig()
    config.hooks.after_apply = ["python -c 'print(1)'"]

    summary = HookRunner(tmp_path, config).run_after_apply()

    assert summary.results[0].executed is False
    assert summary.results[0].exit_code == 125


def test_checkpoint_create_rejects_path_escape(tmp_path: Path) -> None:
    proposal = PatchProposal(
        id="checkpoint-escape",
        task="escape",
        blocks=[PatchBlock(operation="update", file_path=Path("../outside.txt"), search="a", replace="b")],
        created_at="2026-01-01T00:00:00Z",
        model="test",
    )

    try:
        CheckpointManager(tmp_path).create(proposal)
    except PermissionError as exc:
        assert "escapes project root" in str(exc)
    else:
        raise AssertionError("Checkpoint path escape should be rejected.")


def test_rollback_without_checkpoint_has_clear_error(tmp_path: Path) -> None:
    try:
        CheckpointManager(tmp_path).rollback_last()
    except FileNotFoundError as exc:
        assert "No checkpoints found" in str(exc)
    else:
        raise AssertionError("Rollback without checkpoint should fail clearly.")


def test_context_collector_skips_secret_like_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("public", encoding="utf-8")
    (tmp_path / ".env.local").write_text("SECRET=value", encoding="utf-8")
    (tmp_path / "api_token.txt").write_text("token", encoding="utf-8")

    context = ContextCollector(tmp_path).collect()

    assert "README.md" in context["files"]
    assert ".env.local" not in context["files"]
    assert "api_token.txt" not in context["files"]
