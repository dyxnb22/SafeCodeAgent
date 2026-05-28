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
        executable = tokens[0]
        lowered = [token.lower() for token in tokens]

        if executable == "git":
            git_risk = self._git_arg_risk(tokens, lowered)
            if git_risk:
                return git_risk
        if executable in {"python", "python3"}:
            python_risk = self._python_arg_risk(tokens)
            if python_risk:
                return python_risk
        if executable == "node" and "-e" in tokens[1:]:
            return "node -e can execute arbitrary JavaScript."
        if executable in {"npm", "pnpm"} and len(lowered) >= 2 and lowered[1] in {"run", "exec", "dlx"}:
            return f"{executable} {lowered[1]} can execute project-defined scripts."
        if executable in {"pip", "uv"} and "install" in lowered[1:]:
            return "package installation changes the execution environment."
        if executable == "uv" and any(token in {"run", "tool"} for token in lowered[1:]):
            return "uv run/tool can execute project or external code."
        return None

    def _git_arg_risk(self, tokens: list[str], lowered: list[str]) -> str | None:
        """Detect git flags and subcommands that escape the project boundary or shell out."""
        for index, token in enumerate(tokens[1:], start=1):
            if token == "-C" or token.startswith("--work-tree") or token.startswith("--git-dir"):
                return "git path override can operate outside the project boundary."
            if token == "-c":
                if index + 1 >= len(tokens):
                    return "git -c without a key/value is not allowed."
                if self._git_config_is_dangerous(tokens[index + 1]):
                    return "git -c alias or core hook config can execute arbitrary shell."
            if token.startswith("-c") and len(token) > 2 and self._git_config_is_dangerous(token[2:]):
                return "git -c alias or core hook config can execute arbitrary shell."

        if len(lowered) < 2:
            return None

        subcommand = lowered[1]
        if subcommand == "config" and any(self._git_config_is_dangerous(token) for token in tokens[2:]):
            return "git config alias or hook path can persist arbitrary shell execution."
        if subcommand == "reset" and "--hard" in lowered[2:]:
            return "git reset --hard is destructive."
        if subcommand == "clean" and any(flag in lowered[2:] for flag in {"-f", "-df", "-fd", "-fdx", "-dfx", "-fx", "-xf"}):
            return "git clean can delete untracked files."
        if subcommand in {"checkout", "restore"} and "--" in tokens[2:]:
            return f"git {subcommand} -- can overwrite working tree files."
        if subcommand in {"switch", "push"}:
            return f"git {subcommand} changes repository state outside the safe patch flow."
        return None

    def _git_config_is_dangerous(self, token: str) -> bool:
        """Return true for git config keys that can shell out or change hooks."""
        key = token.split("=", 1)[0].lower()
        value = token.split("=", 1)[1] if "=" in token else ""
        return key.startswith("alias.") or key in {"core.hookspath", "core.sshcommand"} or value.startswith("!")

    def _python_arg_risk(self, tokens: list[str]) -> str | None:
        """Detect Python execution modes that bypass patch review."""
        if "-c" in tokens[1:]:
            return "python -c can execute arbitrary code."
        if "-m" in tokens[1:]:
            return "python -m can execute arbitrary modules."
        return None
