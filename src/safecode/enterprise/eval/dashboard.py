"""Markdown eval dashboard renderer."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from safecode.enterprise.eval.cases import EvaluationResult


def render_dashboard(results: list[EvaluationResult]) -> str:
    by_suite: dict[str, list[EvaluationResult]] = defaultdict(list)
    for item in results:
        by_suite[item.suite].append(item)
    lines = ["# Enterprise Evaluation Dashboard", ""]
    budget_violations = 0
    for suite in sorted(by_suite):
        items = by_suite[suite]
        passed = sum(1 for item in items if item.passed)
        lines.append(f"## Suite: {suite}")
        lines.append("")
        lines.append(f"- Passed: {passed}/{len(items)}")
        for item in items:
            budget_ms = item.cost_used.total.latency_ms if item.cost_used else 0
            if budget_ms > 30_000:
                budget_violations += 1
                lines.append(f"- Budget warning: {item.case_id} latency {budget_ms}ms")
        lines.append("")
        lines.append("| Case | Pass | Metrics | Notes |")
        lines.append("|---|---|---|---|")
        for item in items:
            metrics = ", ".join(f"{key}={value:.3f}" for key, value in sorted(item.metrics.items()))
            lines.append(
                f"| {item.case_id} | {'yes' if item.passed else 'no'} | {metrics or '-'} | {item.notes} |"
            )
        lines.append("")
    if budget_violations:
        lines.append(f"**Latency budget warnings:** {budget_violations}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_dashboard(sac_root: Path, markdown: str) -> Path:
    path = sac_root / "enterprise" / "eval" / "latest.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path
