"""Run local evaluation commands."""

from dataclasses import dataclass
from pathlib import Path

from safecode.eval.cases import EvalCase
from safecode.shell.runner import ShellRunner


@dataclass(frozen=True)
class EvalResult:
    """Evaluation result."""

    name: str
    passed: bool
    output: str


class EvalRunner:
    """Run deterministic local eval cases."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def run(self, cases: list[EvalCase]) -> list[EvalResult]:
        """Run eval cases."""
        shell = ShellRunner(self.project_root)
        results: list[EvalResult] = []
        for case in cases:
            result = shell.run(case.command, approved=True)
            output = result.stdout + result.stderr
            results.append(EvalResult(case.name, case.expected_text in output, output))
        return results
