from pathlib import Path

from safecode.config import SafeCodeConfig, merge_trusted_config
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
