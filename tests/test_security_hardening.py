from pathlib import Path

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
