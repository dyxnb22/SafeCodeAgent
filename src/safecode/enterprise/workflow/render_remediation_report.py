"""Markdown renderer for remediation reports."""

from __future__ import annotations

from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks.remediation import code_citations, policy_citations
from safecode.enterprise.workflow.types import RiskTier


def render_remediation_report(state: EnterpriseRunState) -> str:
    risk = state.risk_tier.value if state.risk_tier else RiskTier.low.value
    lines = [
        "# Remediation Report",
        "",
        "## Summary",
        "",
        f"- Run: `{state.run_id}`",
        f"- Findings: {len(state.findings)}",
        f"- Risk: **{risk}**",
        "",
        "## Findings",
        "",
    ]
    for finding in state.findings:
        lines.append(
            f"- **{finding.title}** ({finding.rule_id}) at "
            f"`{finding.location.path}:{finding.location.start_line}`"
        )
    lines.extend(["", "## Cited Policies", ""])
    policies = policy_citations(state.citations)
    if policies:
        for item in policies:
            lines.append(f"- `{item.path}` L{item.start_line}-L{item.end_line}")
    else:
        lines.append("- None")
    lines.extend(["", "## Cited Code", ""])
    code = code_citations(state.citations)
    if code:
        for item in code:
            lines.append(f"- `{item.path}` L{item.start_line}-L{item.end_line}")
    else:
        lines.append("- None")
    lines.extend(["", "## Patch Proposal", ""])
    patch_props = [item for item in state.proposals if item.kind == "patch"]
    if patch_props:
        lines.append(f"- `{patch_props[0].ref}`")
    else:
        lines.append("- No automated patch proposed.")
    lines.extend(["", "## Validation", ""])
    if state.validation:
        lines.append(f"- {state.validation.summary}")
        for key, value in state.validation.details.items():
            lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)
