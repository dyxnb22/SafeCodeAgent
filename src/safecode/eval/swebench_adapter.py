"""SWE-bench Lite compatible eval harness (v6.5.0).

Provides a task format compatible with SWE-bench Lite, a runner that adapts
tasks to the existing TaskReplayRunner, and a report generator.

Design goals:
- Read SWE-bench-Lite-shaped JSON task files from a directory.
- Convert each task to a TaskEvalFixture and run it through TaskReplayRunner.
- Emit a structured JSON report that can be committed to snapshots/.
- No live network calls by default (mock provider); real providers via --provider.
- Honest about pass rate: the report states instance count and result per task.

SWEBenchTask JSON schema (schema_version=1):

    {
      "schema_version": 1,
      "instance_id": "project__issue-42",
      "problem_statement": "The divide() function crashes on zero...",
      "repo": {
        "kind": "inline",
        "files": {"calc.py": "def divide(a, b): return a / b"},
        "setup_commands": []
      },
      "test_command": "python -m pytest tests/ -q",
      "pass_condition": "exit_code_0",
      "hints": ""
    }

pass_condition values:
  "exit_code_0"         — test command must exit 0.
  "output_contains:<s>" — combined stdout+stderr must contain <s>.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safecode.eval.fixtures import (
    ExpectedOutcome,
    RepoFixture,
    SafetyExpectations,
    TaskEvalFixture,
)
from safecode.eval.runner import ReplayResult, TaskReplayRunner

SWEBENCH_SCHEMA_VERSION = 1
_SNAPSHOT_DIR = Path(__file__).parent.parent.parent.parent / "tests" / "snapshots" / "swebench_lite"


# ---------------------------------------------------------------------------
# Task model
# ---------------------------------------------------------------------------


@dataclass
class SWEBenchTask:
    """One SWE-bench-Lite-compatible eval task."""

    instance_id: str
    problem_statement: str
    repo: dict[str, Any]          # serialised RepoFixture dict
    test_command: str             # run after patch to check pass
    pass_condition: str           # "exit_code_0" | "output_contains:<text>"
    schema_version: int = SWEBENCH_SCHEMA_VERSION
    hints: str = ""


@dataclass
class SWEBenchTaskResult:
    """Result of running one SWE-bench task."""

    instance_id: str
    passed: bool
    exit_code: int | None
    output_snippet: str           # first 300 chars of combined output
    failure_reasons: list[str]
    wall_seconds: float
    stopped_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "passed": self.passed,
            "exit_code": self.exit_code,
            "output_snippet": self.output_snippet,
            "failure_reasons": self.failure_reasons,
            "wall_seconds": round(self.wall_seconds, 2),
            "stopped_reason": self.stopped_reason,
        }


@dataclass
class SWEBenchReport:
    """Aggregated report for a suite run."""

    suite: str
    run_at: str
    provider: str
    total: int
    passed: int
    results: list[SWEBenchTaskResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "run_at": self.run_at,
            "provider": self.provider,
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 3),
            "results": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------


class SWEBenchLoadError(ValueError):
    pass


def load_task_from_dict(data: dict[str, Any]) -> SWEBenchTask:
    """Validate and parse a task dict. Raises SWEBenchLoadError on failure."""
    if not isinstance(data, dict):
        raise SWEBenchLoadError("Task must be a JSON object.")
    version = data.get("schema_version", 1)
    if version != SWEBENCH_SCHEMA_VERSION:
        raise SWEBenchLoadError(f"Unsupported schema_version: {version!r}.")
    required = ["instance_id", "problem_statement", "repo", "test_command", "pass_condition"]
    for key in required:
        if not data.get(key):
            raise SWEBenchLoadError(f"Missing required field: {key!r}.")
    return SWEBenchTask(
        instance_id=str(data["instance_id"]),
        problem_statement=str(data["problem_statement"]),
        repo=dict(data["repo"]),
        test_command=str(data["test_command"]),
        pass_condition=str(data["pass_condition"]),
        schema_version=int(version),
        hints=str(data.get("hints", "")),
    )


def load_tasks_from_dir(directory: Path) -> list[SWEBenchTask]:
    """Load all *.json task files from directory. Collects errors."""
    errors: list[str] = []
    tasks: list[SWEBenchTask] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            tasks.append(load_task_from_dict(data))
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    if errors and not tasks:
        raise SWEBenchLoadError("No valid tasks loaded:\n" + "\n".join(errors))
    return tasks


# ---------------------------------------------------------------------------
# Adapter: SWEBenchTask → TaskEvalFixture
# ---------------------------------------------------------------------------


def task_to_fixture(task: SWEBenchTask) -> TaskEvalFixture:
    """Convert a SWEBenchTask to a TaskEvalFixture for TaskReplayRunner."""
    repo = RepoFixture.model_validate(task.repo)

    # Determine pass condition for the fixture
    if task.pass_condition == "exit_code_0":
        expected = ExpectedOutcome(kind="any", expected_exit_code=0)
        validation_commands = [task.test_command]
    elif task.pass_condition.startswith("output_contains:"):
        needle = task.pass_condition[len("output_contains:"):]
        expected = ExpectedOutcome(kind="any", expected_output_contains=[needle])
        validation_commands = [task.test_command]
    else:
        expected = ExpectedOutcome(kind="any")
        validation_commands = [task.test_command]

    goal = task.problem_statement
    if task.hints:
        goal = f"{goal}\n\nHints: {task.hints}"

    return TaskEvalFixture(
        name=task.instance_id,
        goal=goal,
        repo=repo,
        expected=expected,
        safety=SafetyExpectations(
            expect_diff_review=True,
            expect_checkpoint=True,
            expect_approval_gate=True,
            allow_network=False,
        ),
        description=f"SWE-bench Lite: {task.instance_id}",
        tags=["swebench-lite"],
        validation_commands=validation_commands,
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class SWEBenchRunner:
    """Runs SWE-bench Lite tasks through the existing TaskReplayRunner."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._replay_runner = TaskReplayRunner()

    def run(self, task: SWEBenchTask) -> SWEBenchTaskResult:
        """Run one task and return its result."""
        fixture = task_to_fixture(task)
        t0 = time.monotonic()
        try:
            replay = self._replay_runner.run(fixture)
        except Exception as exc:
            return SWEBenchTaskResult(
                instance_id=task.instance_id,
                passed=False,
                exit_code=None,
                output_snippet=str(exc)[:300],
                failure_reasons=[f"runner_error: {type(exc).__name__}"],
                wall_seconds=time.monotonic() - t0,
                stopped_reason="error",
            )
        wall = time.monotonic() - t0
        return self._replay_to_result(task.instance_id, replay, wall)

    def run_suite(
        self,
        tasks: list[SWEBenchTask],
        limit: int | None = None,
        provider: str = "mock",
    ) -> SWEBenchReport:
        """Run up to `limit` tasks and return an aggregated report."""
        subset = tasks[:limit] if limit else tasks
        results: list[SWEBenchTaskResult] = []
        for task in subset:
            results.append(self.run(task))
        passed = sum(1 for r in results if r.passed)
        return SWEBenchReport(
            suite="swebench-lite",
            run_at=datetime.now(timezone.utc).isoformat(),
            provider=provider,
            total=len(results),
            passed=passed,
            results=results,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _replay_to_result(instance_id: str, replay: ReplayResult, wall: float) -> SWEBenchTaskResult:
        from safecode.eval.runner import ValidationCommandResult
        # Gather combined output from validation details
        combined_output = ""
        exit_code: int | None = None
        for vd in replay.validation_details:
            if isinstance(vd, ValidationCommandResult):
                combined_output += (vd.stdout or "") + (vd.stderr or "")
                if exit_code is None:
                    exit_code = vd.exit_code
            elif isinstance(vd, dict):
                combined_output += (vd.get("stdout") or "") + (vd.get("stderr") or "")
                if exit_code is None and "exit_code" in vd:
                    exit_code = int(vd["exit_code"])

        failures = [f.reason for f in replay.classified_failures] if replay.classified_failures else []
        if replay.failure_reasons:
            failures.extend(replay.failure_reasons)
        failures = failures[:5]  # cap

        return SWEBenchTaskResult(
            instance_id=instance_id,
            passed=replay.passed,
            exit_code=exit_code,
            output_snippet=combined_output[:300],
            failure_reasons=failures,
            wall_seconds=round(wall, 2),
            stopped_reason=replay.error or ("passed" if replay.passed else "failed"),
        )


# ---------------------------------------------------------------------------
# Report I/O
# ---------------------------------------------------------------------------


def save_report(report: SWEBenchReport, out_dir: Path | None = None) -> Path:
    """Save the report JSON to the snapshots dir. Returns the written path."""
    target_dir = out_dir or _SNAPSHOT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    latest = target_dir / "latest.json"
    latest.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return latest


def render_report_text(report: SWEBenchReport) -> str:
    """Format a human-readable summary."""
    lines = [
        f"SWE-bench Lite Eval — {report.suite}",
        f"Provider : {report.provider}",
        f"Run at   : {report.run_at}",
        f"Results  : {report.passed}/{report.total} passed ({report.pass_rate:.0%})",
        "",
    ]
    for r in report.results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{status}] {r.instance_id}  ({r.wall_seconds:.1f}s)")
        if not r.passed and r.failure_reasons:
            lines.append(f"        → {r.failure_reasons[0]}")
    return "\n".join(lines)
