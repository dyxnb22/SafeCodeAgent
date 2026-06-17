"""Real-task benchmark helpers for v7.1.4.

The real-task lane reuses SWE-bench-Lite-compatible task files but filters out
synthetic SafeCode micro-fixtures. This keeps the runner small while making the
benchmark provenance explicit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from safecode.eval.swebench_adapter import (
    SWEBenchReport,
    SWEBenchRunner,
    SWEBenchTask,
    load_tasks_from_dir,
    render_report_text,
)

_DEFAULT_SUITE_DIR = (
    Path(__file__).parent.parent.parent.parent / "tests" / "eval_fixtures" / "swebench_lite"
)
_DEFAULT_REPORT_DIR = Path(".sac") / "eval" / "real-task"


@dataclass(frozen=True)
class RealTaskBenchmarkManifest:
    """Manifest describing the selected real-task benchmark slice."""

    suite: str
    source_suite: str
    total: int
    task_ids: list[str]
    selection_rule: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "source_suite": self.source_suite,
            "total": self.total,
            "task_ids": list(self.task_ids),
            "selection_rule": self.selection_rule,
        }


def is_real_task(task: SWEBenchTask) -> bool:
    """Return True for tasks derived from external project issues."""
    return not task.instance_id.startswith("safecode__")


def load_default_real_tasks(suite_dir: Path | None = None) -> list[SWEBenchTask]:
    """Load built-in real-task benchmark tasks."""
    tasks = load_tasks_from_dir(suite_dir or _DEFAULT_SUITE_DIR)
    return [task for task in tasks if is_real_task(task)]


def build_real_task_manifest(tasks: list[SWEBenchTask]) -> RealTaskBenchmarkManifest:
    """Build a provenance manifest for a selected real-task slice."""
    return RealTaskBenchmarkManifest(
        suite="real-task",
        source_suite="swebench-lite",
        total=len(tasks),
        task_ids=[task.instance_id for task in tasks],
        selection_rule="include tasks whose instance_id does not start with safecode__",
    )


def run_real_task_benchmark(
    *,
    suite_dir: Path | None = None,
    limit: int = 10,
    provider: str = "mock",
    runner: SWEBenchRunner | None = None,
) -> SWEBenchReport:
    """Run the real-task benchmark slice through the SWE-bench adapter."""
    tasks = load_default_real_tasks(suite_dir)
    selected = tasks[:limit] if limit else tasks
    active_runner = runner or SWEBenchRunner(project_root=Path.cwd())
    report = active_runner.run_suite(selected, limit=None, provider=provider)
    report.suite = "real-task"
    return report


def save_real_task_report(report: SWEBenchReport, out_dir: Path | None = None) -> Path:
    """Save the real-task report JSON and return the path."""
    target = out_dir or _DEFAULT_REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    path = target / "latest.json"
    path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def render_real_task_report(report: SWEBenchReport, manifest: RealTaskBenchmarkManifest) -> str:
    """Render a human-readable real-task benchmark summary."""
    header = [
        "Real-task Benchmark",
        f"Source suite : {manifest.source_suite}",
        f"Selection    : {manifest.selection_rule}",
        f"Tasks        : {', '.join(manifest.task_ids) if manifest.task_ids else '(none)'}",
        "",
    ]
    return "\n".join(header) + render_report_text(report)
