"""Quality dashboard renderer for TaskReplayRunner / ReplayResult outputs (v2.5.3).

Renders a list of ``ReplayResult`` objects into Markdown or HTML.  Output is
deterministic and snapshot-friendly: given the same inputs the output is always
byte-identical.

No external dependencies beyond the Python standard library.
"""

from __future__ import annotations

import html as _html_mod
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from safecode.eval.failures import FailureCategory
from safecode.eval.runner import ReplayResult


def _markdown_table_cell(value: object) -> str:
    """Escape text for use inside a Markdown table cell."""
    return str(value).replace("|", "\\|")


# ── Summary model ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReportSummary:
    """Aggregated statistics for a collection of replay results.

    ``category_counts`` maps each ``FailureCategory`` value that appears to
    the number of ``ClassifiedFailure`` objects with that category across *all*
    results.  Categories with zero occurrences are omitted.

    ``pass_rate`` is expressed as a float in [0.0, 1.0].  It is ``1.0`` when
    ``total == 0`` (vacuously passing).
    """

    total: int
    passed: int
    failed: int
    pass_rate: float
    category_counts: dict[str, int]


def build_summary(results: Sequence[ReplayResult]) -> ReportSummary:
    """Build a ``ReportSummary`` from a sequence of ``ReplayResult`` objects."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    pass_rate = (passed / total) if total > 0 else 1.0

    counts: Counter[str] = Counter()
    for result in results:
        for cf in result.classified_failures:
            counts[cf.category.value] += 1

    # Deterministic order: sort by category name (FailureCategory enum order, then alpha)
    ordered_cats = [c.value for c in FailureCategory]
    category_counts: dict[str, int] = {}
    for cat in ordered_cats:
        if cat in counts:
            category_counts[cat] = counts[cat]
    # Any category not in the enum (future-proofing) goes last, sorted alpha
    for cat in sorted(counts):
        if cat not in category_counts:
            category_counts[cat] = counts[cat]

    return ReportSummary(
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
        category_counts=category_counts,
    )


# ── Renderer ────────────────────────────────────────────────────────────────


class DashboardRenderer:
    """Render ``ReplayResult`` lists as Markdown or HTML dashboard reports.

    Both renderers are deterministic: given the same inputs and title the
    output is always byte-identical.
    """

    # ── Markdown ─────────────────────────────────────────────────────────────

    def render_markdown(
        self,
        results: Sequence[ReplayResult],
        title: str = "Eval Report",
    ) -> str:
        """Render *results* as a Markdown dashboard string."""
        summary = build_summary(results)
        lines: list[str] = []

        lines += [f"# {title}", ""]

        # Summary section
        lines += [
            "## Summary",
            "",
            f"- **Total fixtures:** {summary.total}",
            f"- **Passed:** {summary.passed}",
            f"- **Failed:** {summary.failed}",
            f"- **Pass rate:** {summary.pass_rate:.1%}",
            "",
        ]

        # Failure category counts
        if summary.category_counts:
            lines += ["## Failure Categories", ""]
            lines += ["| Category | Count |", "|---|---|"]
            for cat, count in summary.category_counts.items():
                lines.append(f"| {_markdown_table_cell(cat)} | {count} |")
            lines.append("")

        # Per-fixture results
        lines += ["## Fixture Results", ""]
        if not results:
            lines += ["*No results.*", ""]
        else:
            lines += ["| Fixture | Status | Network | Audit Events | Failure Reasons |", "|---|---|---|---|---|"]
            for result in results:
                status = "PASS" if result.passed else "FAIL"
                reasons_cell = "; ".join(result.failure_reasons) if result.failure_reasons else ""
                lines.append(
                    f"| {_markdown_table_cell(result.fixture_name)} | {status} "
                    f"| {_markdown_table_cell(result.network_intent)} "
                    f"| {_markdown_table_cell(result.audit_events_status)} "
                    f"| {_markdown_table_cell(reasons_cell)} |"
                )
            lines.append("")

        # Per-fixture detail (failures only)
        failed_results = [r for r in results if not r.passed]
        if failed_results:
            lines += ["## Failure Details", ""]
            for result in failed_results:
                lines += [f"### {result.fixture_name}", ""]

                if result.error:
                    lines += [f"**Error:** {result.error}", ""]

                if result.failure_reasons:
                    lines += ["**Failure reasons:**", ""]
                    for reason in result.failure_reasons:
                        lines.append(f"- {reason}")
                    lines.append("")

                if result.forbidden_commands_violated:
                    lines += ["**Forbidden commands violated:**", ""]
                    for cmd in result.forbidden_commands_violated:
                        lines.append(f"- `{cmd}`")
                    lines.append("")

                if result.forbidden_file_writes_violated:
                    lines += ["**Forbidden file writes violated:**", ""]
                    for fw in result.forbidden_file_writes_violated:
                        lines.append(f"- `{fw}`")
                    lines.append("")

                if result.classified_failures:
                    lines += ["**Classified failures:**", ""]
                    lines += ["| Category | Reason | Detail |", "|---|---|---|"]
                    for cf in result.classified_failures:
                        detail = cf.detail or ""
                        lines.append(
                            f"| {_markdown_table_cell(cf.category.value)} "
                            f"| {_markdown_table_cell(cf.reason)} "
                            f"| {_markdown_table_cell(detail)} |"
                        )
                    lines.append("")

        return "\n".join(lines)

    # ── HTML ─────────────────────────────────────────────────────────────────

    def render_html(
        self,
        results: Sequence[ReplayResult],
        title: str = "Eval Report",
    ) -> str:
        """Render *results* as a self-contained HTML dashboard string."""
        summary = build_summary(results)
        e = _html_mod.escape  # alias for readability

        parts: list[str] = []

        parts.append(
            f"<!DOCTYPE html>\n"
            f"<html lang=\"en\">\n"
            f"<head>\n"
            f"<meta charset=\"utf-8\">\n"
            f"<title>{e(title)}</title>\n"
            f"<style>\n"
            f"body{{font-family:sans-serif;margin:2em;color:#222}}\n"
            f"table{{border-collapse:collapse;margin-bottom:1em}}\n"
            f"th,td{{border:1px solid #ccc;padding:.4em .8em;text-align:left}}\n"
            f"th{{background:#f0f0f0}}\n"
            f".pass{{color:#2a7a2a;font-weight:bold}}\n"
            f".fail{{color:#b00;font-weight:bold}}\n"
            f"h1{{border-bottom:2px solid #ccc;padding-bottom:.3em}}\n"
            f"h2{{margin-top:1.5em}}\n"
            f"h3{{margin-top:1em}}\n"
            f"</style>\n"
            f"</head>\n"
            f"<body>\n"
            f"<h1>{e(title)}</h1>\n"
        )

        # Summary section
        parts.append("<h2>Summary</h2>\n<ul>\n")
        parts.append(f"<li><strong>Total fixtures:</strong> {summary.total}</li>\n")
        parts.append(f"<li><strong>Passed:</strong> {summary.passed}</li>\n")
        parts.append(f"<li><strong>Failed:</strong> {summary.failed}</li>\n")
        parts.append(f"<li><strong>Pass rate:</strong> {summary.pass_rate:.1%}</li>\n")
        parts.append("</ul>\n")

        # Failure category counts
        if summary.category_counts:
            parts.append("<h2>Failure Categories</h2>\n")
            parts.append("<table>\n<tr><th>Category</th><th>Count</th></tr>\n")
            for cat, count in summary.category_counts.items():
                parts.append(f"<tr><td>{e(cat)}</td><td>{count}</td></tr>\n")
            parts.append("</table>\n")

        # Per-fixture results table
        parts.append("<h2>Fixture Results</h2>\n")
        if not results:
            parts.append("<p><em>No results.</em></p>\n")
        else:
            parts.append(
                "<table>\n"
                "<tr><th>Fixture</th><th>Status</th><th>Network</th>"
                "<th>Audit Events</th><th>Failure Reasons</th></tr>\n"
            )
            for result in results:
                status_class = "pass" if result.passed else "fail"
                status_text = "PASS" if result.passed else "FAIL"
                reasons_html = e("; ".join(result.failure_reasons)) if result.failure_reasons else ""
                parts.append(
                    f"<tr>"
                    f"<td>{e(result.fixture_name)}</td>"
                    f"<td class=\"{status_class}\">{status_text}</td>"
                    f"<td>{e(result.network_intent)}</td>"
                    f"<td>{e(result.audit_events_status)}</td>"
                    f"<td>{reasons_html}</td>"
                    f"</tr>\n"
                )
            parts.append("</table>\n")

        # Failure details
        failed_results = [r for r in results if not r.passed]
        if failed_results:
            parts.append("<h2>Failure Details</h2>\n")
            for result in failed_results:
                parts.append(f"<h3>{e(result.fixture_name)}</h3>\n")

                if result.error:
                    parts.append(f"<p><strong>Error:</strong> {e(result.error)}</p>\n")

                if result.failure_reasons:
                    parts.append("<p><strong>Failure reasons:</strong></p>\n<ul>\n")
                    for reason in result.failure_reasons:
                        parts.append(f"<li>{e(reason)}</li>\n")
                    parts.append("</ul>\n")

                if result.forbidden_commands_violated:
                    parts.append("<p><strong>Forbidden commands violated:</strong></p>\n<ul>\n")
                    for cmd in result.forbidden_commands_violated:
                        parts.append(f"<li><code>{e(cmd)}</code></li>\n")
                    parts.append("</ul>\n")

                if result.forbidden_file_writes_violated:
                    parts.append("<p><strong>Forbidden file writes violated:</strong></p>\n<ul>\n")
                    for fw in result.forbidden_file_writes_violated:
                        parts.append(f"<li><code>{e(fw)}</code></li>\n")
                    parts.append("</ul>\n")

                if result.classified_failures:
                    parts.append("<p><strong>Classified failures:</strong></p>\n")
                    parts.append("<table>\n<tr><th>Category</th><th>Reason</th><th>Detail</th></tr>\n")
                    for cf in result.classified_failures:
                        detail_html = e(cf.detail) if cf.detail else ""
                        parts.append(
                            f"<tr>"
                            f"<td>{e(cf.category.value)}</td>"
                            f"<td>{e(cf.reason)}</td>"
                            f"<td>{detail_html}</td>"
                            f"</tr>\n"
                        )
                    parts.append("</table>\n")

        parts.append("</body>\n</html>")
        return "".join(parts)
