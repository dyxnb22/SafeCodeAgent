"""Markdown dashboard renderer for run timelines."""

from __future__ import annotations

from safecode.enterprise.trace.timeline import RunTimeline

SECTION_ORDER = (
    "Summary",
    "Timeline",
    "Citations",
    "Tool Calls",
    "Approvals",
    "Validation",
    "Cost and Token Summary",
    "Safety Invariants",
    "Failures",
)


def render_markdown(timeline: RunTimeline) -> str:
  lines: list[str] = []
  lines.extend(_render_summary(timeline))
  lines.append("")
  lines.extend(_render_timeline(timeline))
  lines.append("")
  lines.extend(_render_citations(timeline))
  lines.append("")
  lines.extend(_render_tool_calls(timeline))
  lines.append("")
  lines.extend(_render_approvals(timeline))
  lines.append("")
  lines.extend(_render_validation(timeline))
  lines.append("")
  lines.extend(_render_cost(timeline))
  lines.append("")
  lines.extend(_render_safety(timeline))
  lines.append("")
  lines.extend(_render_failures(timeline))
  return "\n".join(lines).rstrip() + "\n"


def _render_summary(timeline: RunTimeline) -> list[str]:
  total = timeline.costs.get("total", {})
  return [
    "# Enterprise Run Dashboard",
    "",
    "## Summary",
    "",
    f"- **Run ID**: {timeline.run_id}",
    f"- **Tenant**: {timeline.tenant_id}",
    f"- **Task**: {timeline.task_type}",
    f"- **Actor**: {timeline.actor.actor_id} (roles: {', '.join(timeline.actor.roles) or 'none'})",
    f"- **Policy snapshot**: {timeline.policy_snapshot_id}",
    f"- **Status**: {timeline.status}",
    f"- **Started**: {timeline.started_at}",
    f"- **Ended**: {timeline.ended_at or 'n/a'}",
    f"- **Duration**: {timeline.duration_ms} ms",
    (
      "- **Total cost**: "
      f"{total.get('input_tokens', 0)} in / {total.get('output_tokens', 0)} out tokens"
    ),
  ]


def _render_timeline(timeline: RunTimeline) -> list[str]:
  lines = ["## Timeline", "", "| Node | Status | Duration (ms) | Summary |", "|---|---|---:|---|"]
  for node in timeline.nodes:
    lines.append(
      f"| {node.name} | {node.status} | {node.duration_ms} | {node.summary} |"
    )
  return lines


def _render_citations(timeline: RunTimeline) -> list[str]:
  lines = ["## Citations", ""]
  if not timeline.citations:
    lines.append("_No citations recorded._")
    return lines
  lines.extend(
    [
      "| Path | Lines | Score | Permission | Freshness | Reason |",
      "|---|---:|---:|---|---|---|",
    ]
  )
  for cite in timeline.citations:
    lines.append(
      f"| {cite.path} | {cite.start_line}-{cite.end_line} | {cite.score:.2f} | "
      f"{cite.permission_verdict} | {cite.freshness} | {cite.selection_reason} |"
    )
  return lines


def _render_tool_calls(timeline: RunTimeline) -> list[str]:
  lines = ["## Tool Calls", ""]
  if not timeline.tool_calls:
    lines.append("_No tool calls recorded._")
    return lines
  lines.extend(["| Tool | Category | Decision | Outcome | Duration (ms) |", "|---|---|---|---|---:|"])
  for call in timeline.tool_calls:
    lines.append(
      f"| {call.tool_name} | {call.tool_category} | {call.decision} | "
      f"{call.outcome} | {call.duration_ms} |"
    )
  return lines


def _render_approvals(timeline: RunTimeline) -> list[str]:
  lines = ["## Approvals", ""]
  if not timeline.approvals:
    lines.append("_No approvals recorded._")
    return lines
  for approval in timeline.approvals:
    lines.append(
      f"- **{approval.action}** ({approval.risk_tier}): {approval.status} "
      f"— {approval.decision.get('reason', '')}"
    )
  return lines


def _render_validation(timeline: RunTimeline) -> list[str]:
  return [
    "## Validation",
    "",
    f"- Ran: {timeline.validation.ran}",
    f"- Summary: {timeline.validation.summary}",
  ]


def _render_cost(timeline: RunTimeline) -> list[str]:
  lines = ["## Cost and Token Summary", ""]
  by_node = timeline.costs.get("by_node", {})
  if not by_node:
    lines.append("_No per-node cost breakdown._")
    return lines
  lines.extend(["| Node | Input | Output | Latency (ms) |", "|---|---:|---:|---:|"])
  for node_name, cost in sorted(by_node.items()):
    lines.append(
      f"| {node_name} | {cost.get('input_tokens', 0)} | {cost.get('output_tokens', 0)} | "
      f"{cost.get('latency_ms', 0)} |"
    )
  return lines


def _render_safety(timeline: RunTimeline) -> list[str]:
  inv = timeline.safety_invariants
  checks = [
    ("Audit chain intact", inv.audit_chain_intact),
    ("No unauthorized mutation", inv.no_unauthorized_mutation),
    ("No policy block overridden", inv.no_policy_block_overridden),
    ("No grant double-consume", inv.no_grant_double_consume),
    ("Redaction complete", inv.redaction_complete),
  ]
  lines = ["## Safety Invariants", ""]
  for label, ok in checks:
    mark = "✓" if ok else "✗"
    lines.append(f"- {mark} {label}")
  return lines


def _render_failures(timeline: RunTimeline) -> list[str]:
  lines = ["## Failures", ""]
  if not timeline.failures:
    lines.append("_No failures recorded._")
    return lines
  for failure in timeline.failures:
    lines.append(
      f"- **{failure.get('category', 'unknown')}** @ {failure.get('node_name', 'n/a')}: "
      f"{failure.get('message', '')}"
    )
  return lines


def markdown_sections(timeline: RunTimeline) -> list[str]:
  """Return section headings present in rendered Markdown."""
  return list(SECTION_ORDER)
