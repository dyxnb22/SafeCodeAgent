"""Unified command policy for shell, hooks, and future tools.

中文模块说明：Shell/命令统一策略引擎（CommandPolicy）。
- 基于 allowlist 与参数级启发式检测危险子命令；高风险默认拒绝，中风险可要求审批。
- 本地内核策略层，与 Enterprise PolicyResolver 互补；未知可执行体或无 token 时 fail-closed。
"""

from dataclasses import dataclass

from safecode.config import SafeCodeConfig
from safecode.shell.risk import RiskLevel, ShellRisk, ShellRiskClassifier


@dataclass(frozen=True)
class CommandDecision:
    """Policy decision for a command.

    命令策略裁决结果；``allowed=False`` 时不得执行，``requires_approval=True`` 须人类确认后带 approved 重评。
    """

    command: str
    risk: ShellRisk
    allowed: bool
    requires_approval: bool
    reason: str


class CommandPolicy:
    """Evaluate command allowlist and argument-level risks.

    评估命令 allowlist 与参数级风险；依赖 SafeCodeConfig.shell 旋钮。
    安全不变量：可执行名不在 allowlist 则拒绝；block_high_risk 为真时 HIGH 一律拒绝。
    """

    def __init__(self, config: SafeCodeConfig) -> None:
        self.config = config
        self.classifier = ShellRiskClassifier()

    def evaluate(self, command: str, approved: bool = False) -> CommandDecision:
        """Return a command execution decision.

        返回命令是否允许执行；中风险且 require_confirm_for_medium 时需 approved=True。
        """
        risk = self.classifier.classify(command)
        if not risk.tokens:
            return CommandDecision(command, risk, False, False, "No executable tokens found.")

        arg_risk = self._arg_level_risk(risk.tokens)
        if arg_risk:
            # 参数级风险直接升格为 HIGH 并拒绝，不依赖分类器单独评级。
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
        """Detect dangerous subcommands and arguments.

        检测 git/python/npm 等危险参数模式；命中则整条命令拒绝。
        """
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
        """Detect git flags and subcommands that escape the project boundary or shell out.

        检测 git -C、-c、config 等可越界或 shell out 的用法；checkout/merge 等视为改变仓库状态。
        """
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
        if lowered_subcommand in {"switch", "commit", "merge", "rebase"}:
            return f"git {lowered_subcommand} changes repository state outside the safe patch flow."
        if lowered_subcommand in {"pull", "fetch", "clone", "push", "remote", "submodule"}:
            return f"git {lowered_subcommand} can modify repository state or access remote data."
        return None

    def _git_config_is_dangerous(self, token: str) -> bool:
        """Return true for git config keys that can shell out or change hooks.

        危险 git config 键（alias、hookspath、以 ! 开头的值等）可导致任意命令执行。
        """
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
                "credential.helper",
                "core.askpass",
                "core.fsmonitor",
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
