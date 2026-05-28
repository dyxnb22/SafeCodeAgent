"""Unified command policy for shell, hooks, and future tools."""

from dataclasses import dataclass

from safecode.config import SafeCodeConfig
from safecode.shell.risk import RiskLevel, ShellRisk, ShellRiskClassifier


@dataclass(frozen=True)
class CommandDecision:
    """Policy decision for a command."""

    command: str
    risk: ShellRisk
    allowed: bool
    requires_approval: bool
    reason: str


class CommandPolicy:
    """Evaluate command allowlist and argument-level risks."""

    def __init__(self, config: SafeCodeConfig) -> None:
        self.config = config
        self.classifier = ShellRiskClassifier()

    def evaluate(self, command: str, approved: bool = False) -> CommandDecision:
        """Return a command execution decision."""
        risk = self.classifier.classify(command)
        if not risk.tokens:
            return CommandDecision(command, risk, False, False, "No executable tokens found.")

        arg_risk = self._arg_level_risk(risk.tokens)
        if arg_risk:
            high_risk = ShellRisk(RiskLevel.HIGH, [arg_risk], risk.tokens)
            return CommandDecision(command, high_risk, False, False, arg_risk)

        executable = risk.tokens[0]
        if executable not in self.config.shell.allowed_commands:
            return CommandDecision(command, risk, False, False, f"Command is not allowlisted: {executable}")

        if risk.level == RiskLevel.HIGH and self.config.shell.block_high_risk:
            return CommandDecision(command, risk, False, False, "Blocked high-risk command.")

        if risk.level == RiskLevel.MEDIUM and self.config.shell.require_confirm_for_medium and not approved:
            return CommandDecision(command, risk, False, True, "Approval required for medium-risk command.")

        return CommandDecision(command, risk, True, False, "Command allowed.")

    def _arg_level_risk(self, tokens: list[str]) -> str | None:
        """Detect dangerous subcommands and arguments."""
        if len(tokens) >= 3 and tokens[0] == "git" and tokens[1] == "reset" and "--hard" in tokens[2:]:
            return "git reset --hard is destructive."
        if len(tokens) >= 2 and tokens[0] in {"python", "python3"} and "-c" in tokens[1:]:
            return "python -c can execute arbitrary code."
        if len(tokens) >= 2 and tokens[0] in {"pip", "uv"} and "install" in tokens[1:]:
            return "package installation changes the execution environment."
        return None
