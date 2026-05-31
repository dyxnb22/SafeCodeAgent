"""Classify shell commands before execution."""

import shlex
from dataclasses import dataclass, field
from enum import StrEnum


class RiskLevel(StrEnum):
    """Simple command risk levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class ShellRisk:
    """Risk classification result."""

    level: RiskLevel
    reasons: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)


HIGH_RISK_TOKENS = {
    "sudo",
    "su",
    "rm",
    "chmod",
    "chown",
    "mkfs",
    "dd",
    "shutdown",
    "reboot",
}
MEDIUM_RISK_TOKENS = {
    "git",
    "uv",
    "pip",
    "python",
    "python3",
    "pytest",
    "ruff",
    "npm",
    "pnpm",
    "node",
    "gradle",
    "mvn",
    "go",
    "cargo",
}
LOW_RISK_TOKENS = {
    "pwd",
    "ls",
    "echo",
    "git",
}
SHELL_OPERATORS = {"|", ">", ">>", "<", "&&", "||", ";", "$(", "`"}


class ShellRiskClassifier:
    """Classify commands using conservative string and token checks."""

    def classify(self, command: str) -> ShellRisk:
        """Return the risk level and reasons for a command."""
        reasons: list[str] = []
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            return ShellRisk(RiskLevel.HIGH, [f"cannot parse shell command: {exc}"], [])

        if not tokens:
            return ShellRisk(RiskLevel.LOW, ["empty command"], [])

        raw = command.strip()
        for operator in SHELL_OPERATORS:
            if operator in raw:
                reasons.append(f"contains shell operator {operator!r}")

        lowered = [token.lower() for token in tokens]
        first = lowered[0]

        if first in HIGH_RISK_TOKENS:
            reasons.append(f"starts with high-risk command {first!r}")
        if "curl" in lowered and "|" in raw and ("sh" in lowered or "bash" in lowered):
            reasons.append("downloads and pipes into a shell")
        if "rm" in lowered and ("-rf" in lowered or "-fr" in lowered):
            reasons.append("recursive force delete")

        if reasons:
            return ShellRisk(RiskLevel.HIGH, reasons, tokens)

        if first in LOW_RISK_TOKENS and first != "git":
            return ShellRisk(RiskLevel.LOW, [f"known read-only command {first!r}"], tokens)

        if first in MEDIUM_RISK_TOKENS:
            return ShellRisk(RiskLevel.MEDIUM, [f"known developer command {first!r}"], tokens)

        return ShellRisk(RiskLevel.MEDIUM, ["unknown command requires approval"], tokens)
