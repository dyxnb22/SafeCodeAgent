"""Markdown dashboard for eval reports (v7.1.5)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvalDashboardSource:
    """Summary for one eval report source."""

    name: str
    path: Path
    total: int
    passed: int
    failures: list[str] = field(default_factory=list)
    present: bool = True

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "present": self.present,
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 3),
            "failures": list(self.failures),
        }


def summarize_eval_json(name: str, path: Path) -> EvalDashboardSource:
    """Summarize a live/SWE/real-task eval JSON report."""
    if not path.exists():
        return EvalDashboardSource(name=name, path=path, total=0, passed=0, present=False)
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results", [])
    failures: list[str] = []
    passed = 0
    for item in results:
        ok = bool(item.get("success", item.get("passed", False)))
        if ok:
            passed += 1
            continue
        label = item.get("fixture_name") or item.get("instance_id") or "<unknown>"
        reasons = item.get("failure_reasons") or []
        detail = reasons[0] if reasons else item.get("error") or "failed"
        failures.append(f"{label}: {detail}")
    return EvalDashboardSource(
        name=name,
        path=path,
        total=len(results),
        passed=passed,
        failures=failures,
        present=True,
    )


def default_eval_report_paths(project_root: Path) -> dict[str, Path]:
    """Return the default report locations used by eval commands."""
    return {
        "live": project_root / "tests" / "snapshots" / "live_eval" / "latest.json",
        "swebench-lite": project_root / "tests" / "snapshots" / "swebench_lite" / "latest.json",
        "real-task": project_root / ".sac" / "eval" / "real-task" / "latest.json",
    }


def build_eval_dashboard_sources(project_root: Path) -> list[EvalDashboardSource]:
    """Load summaries for the default eval report locations."""
    return [
        summarize_eval_json(name, path)
        for name, path in default_eval_report_paths(project_root).items()
    ]


def render_eval_dashboard(sources: list[EvalDashboardSource]) -> str:
    """Render a compact Markdown eval dashboard."""
    total = sum(source.total for source in sources)
    passed = sum(source.passed for source in sources)
    pass_rate = passed / total if total else 0.0
    lines = [
        "# SafeCode Eval Dashboard",
        "",
        f"Overall: {passed}/{total} passed ({pass_rate:.1%})",
        "",
        "| Suite | Status | Passed | Pass Rate | Report |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for source in sources:
        status = "present" if source.present else "missing"
        lines.append(
            f"| {source.name} | {status} | {source.passed}/{source.total} | "
            f"{source.pass_rate:.1%} | `{source.path}` |"
        )
    failures = [failure for source in sources for failure in source.failures]
    lines.extend(["", "## Failures"])
    if not failures:
        lines.append("")
        lines.append("No failing eval results found in available reports.")
    else:
        lines.append("")
        for failure in failures:
            lines.append(f"- {failure}")
    return "\n".join(lines) + "\n"


def write_eval_dashboard(project_root: Path, output: Path) -> Path:
    """Write the default eval dashboard to disk."""
    sources = build_eval_dashboard_sources(project_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_eval_dashboard(sources), encoding="utf-8")
    return output
