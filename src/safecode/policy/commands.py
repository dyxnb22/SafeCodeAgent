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
        if executable == "node" and any(token in {"-e", "--eval"} for token in tokens[1:]):
            return "node eval can execute arbitrary JavaScript."
        if executable in {"npm", "pnpm"} and len(lowered) >= 2 and lowered[1] in {"run", "exec", "dlx"}:
            return f"{executable} {lowered[1]} can execute project-defined scripts."
        if executable == "npx":
            return "npx can execute external packages."
        if executable in {"pip", "pip3", "pipx", "uv"} and "install" in lowered[1:]:
            return "package installation changes the execution environment."
        if executable == "uv" and "pip" in lowered[1:]:
            return "uv pip can change the execution environment."
        if executable == "uv" and any(token in {"run", "tool"} for token in lowered[1:]):
            return "uv run/tool can execute project or external code."
        return None

    def _git_arg_risk(self, tokens: list[str], lowered: list[str]) -> str | None:
        """Detect git flags and subcommands that escape the project boundary or shell out."""
        for index, token in enumerate(tokens[1:], start=1):
            if token == "-C" or token.startswith("-C") or token.startswith("--work-tree") or token.startswith("--git-dir"):
                return "git path override can operate outside the project boundary."
            if token == "-c":
                if index + 1 >= len(tokens):
                    return "git -c without a key/value is not allowed."
                if self._git_config_is_dangerous(tokens[index + 1]):
                    return "git -c config can load external config or execute arbitrary shell."
            if token.startswith("-c") and len(token) > 2 and self._git_config_is_dangerous(token[2:]):
                return "git -c config can load external config or execute arbitrary shell."

        subcommand, subcommand_index = self._git_subcommand(tokens)
        if not subcommand:
            return None

        lowered_subcommand = subcommand.lower()
        tail_tokens = tokens[subcommand_index + 1 :]
        lowered_tail = [token.lower() for token in tail_tokens]

        if lowered_subcommand == "config" and any(self._git_config_is_dangerous(token) for token in tail_tokens):
            return "git config can persist unsafe configuration."
        if lowered_subcommand == "reset" and "--hard" in lowered_tail:
            return "git reset --hard is destructive."
        if lowered_subcommand == "clean":
            return "git clean can delete untracked files."
        if lowered_subcommand in {"checkout", "restore"}:
            return f"git {lowered_subcommand} -- can overwrite working tree files."
        if lowered_subcommand in {"switch", "push"}:
            return f"git {lowered_subcommand} changes repository state outside the safe patch flow."
        return None

    def _git_config_is_dangerous(self, token: str) -> bool:
        """Return true for git config keys that can shell out or change hooks."""
        key = token.split("=", 1)[0].lower()
        value = token.split("=", 1)[1] if "=" in token else ""
        return (
            key.startswith("alias.")
            or key.startswith("pager.")
            or (key.startswith("diff.") and key.endswith(".command"))
            or key == "include.path"
            or (key.startswith("includeif.") and key.endswith(".path"))
            or key
            in {
                "core.hookspath",
                "core.sshcommand",
                "core.pager",
                "core.editor",
                "sequence.editor",
            }
            or value.startswith("!")
        )

    def _git_subcommand(self, tokens: list[str]) -> tuple[str | None, int]:
        """Return the git subcommand and its index."""
        index = 1
        while index < len(tokens):
            token = tokens[index]
            if token in {"-c", "-C"}:
                index += 2
                continue
            if token in {"--work-tree", "--git-dir"}:
                index += 2
                continue
            if token.startswith("-c") or token.startswith("-C"):
                index += 1
                continue
            if token.startswith("--work-tree") or token.startswith("--git-dir"):
                index += 1
                continue
            if token.startswith("-"):
                index += 1
                continue
            return token, index
        return None, -1

    def _python_arg_risk(self, tokens: list[str]) -> str | None:
        """Detect Python execution modes that bypass patch review."""
        if "-c" in tokens[1:]:
            return "python -c can execute arbitrary code."
        if "-m" in tokens[1:]:
            return "python -m can execute arbitrary modules."
        if "-" in tokens[1:]:
            return "python - can execute code from stdin."
        return None
