"""Markdown renderer for secure implementation planning reports."""

from __future__ import annotations

from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks.secure_planning import policy_citations, code_citations
from safecode.enterprise.workflow.types import RiskTier


def _format_citation_line(citation_id: str, path: str, score: float) -> str:
    return f"- `{citation_id}` — `{path}` (score={score:.2f})"


def render_planning_report(state: EnterpriseRunState) -> str:
    plan = state.plan
    risk = state.risk_tier.value if state.risk_tier else RiskTier.medium.value
    evidence = state.issue_evidence
    lines = [
        "# Secure Implementation Plan",
        "",
        "## Summary",
        "",
        f"- Run: `{state.run_id}`",
        f"- Task: `{state.task_type.value}`",
        f"- Ticket: `{evidence.issue_id if evidence else 'unknown'}`",
        f"- Overall risk: **{risk}**",
        "",
    ]
    if plan is not None:
        lines.extend(
            [
                f"**Plan:** {plan.summary}",
                "",
                "## Planned Actions",
                "",
            ]
        )
        for action in plan.actions:
            approval = " (approval required)" if action.requires_approval else ""
            lines.append(f"- {action.title}{approval}")
        lines.append("")
        if plan.alternatives:
            lines.append("## Alternatives")
            lines.append("")
            for alt in plan.alternatives:
                lines.append(f"- {alt}")
            lines.append("")
        if plan.revisit_trigger:
            lines.extend(["## Revisit Trigger", "", plan.revisit_trigger, ""])
        if plan.citation_ids:
            lines.extend(["## Citation IDs", ""])
            for citation_id in plan.citation_ids:
                lines.append(f"- `{citation_id}`")
            lines.append("")

    policies = policy_citations(state.citations)
    code = code_citations(state.citations)
    lines.extend(["## Policy Citations", ""])
    if policies:
        for item in policies:
            lines.append(_format_citation_line(item.citation_id, item.path, item.score))
    else:
        lines.append("No policy citations retrieved.")
    lines.extend(["", "## Code Citations", ""])
    if code:
        for item in code:
            lines.append(_format_citation_line(item.citation_id, item.path, item.score))
    else:
        lines.append("No code citations retrieved.")
    lines.append("")
    if state.findings:
        lines.extend(["## Security Considerations", ""])
        for finding in state.findings:
            lines.append(f"- **{finding.title}** (`{finding.rule_id}`): {finding.description}")
        lines.append("")
    return "\n".join(lines)
