"""Run configured project hooks through the controlled shell runner."""

from dataclasses import dataclass
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.shell.runner import ShellRunResult, ShellRunner


@dataclass(frozen=True)
class HookRunSummary:
    """Hook execution summary."""

    hook_name: str
    results: list[ShellRunResult]


class HookRunner:
    """Run hooks defined in SafeCodeConfig."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root
        self.config = config or SafeCodeConfig.load(project_root)

    def run_after_apply(self) -> HookRunSummary:
        """Run after_apply commands."""
        runner = ShellRunner(self.project_root, self.config)
        results = [runner.run(command, approved=True) for command in self.config.hooks.after_apply]
        return HookRunSummary("after_apply", results)
