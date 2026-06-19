"""Markdown renderer for PR security review reports."""

from __future__ import annotations

from safecode.enterprise.rag.models import Citation
from safecode.enterprise.rag.source_registry import SourceType
from safecode.enterprise.workflow.state import EnterpriseRunState, SecurityFinding
from safecode.enterprise.workflow.tasks.pr_review import code_citations, policy_citations
from safecode.enterprise.workflow.types import RiskTier

_RISK_ORDER = [RiskTier.critical, RiskTier.high, RiskTier.medium, RiskTier.low]


def _sort_findings(findings: list[SecurityFinding]) -> list[SecurityFinding]:
    return sorted(findings, key=lambda item: _RISK_ORDER.index(item.severity))


def _format_citation(citation: Citation) -> str:
    return (
        f"- `{citation.path}` L{citation.start_line}-L{citation.end_line} "
        f"(score={citation.score:.2f}, {citation.permission_verdict})"
    )


def render_pr_report(state: EnterpriseRunState) -> str:
    findings = _sort_findings(state.findings)
    risk = state.risk_tier.value if state.risk_tier else RiskTier.low.value
    policies = policy_citations(state.citations)
    code = code_citations(state.citations)
    lines = [
        "# PR Security Review Report",
        "",
        "## Summary",
        "",
        f"- Run: `{state.run_id}`",
        f"- Task: `{state.task_type.value}`",
        f"- Overall risk: **{risk}**",
        f"- Findings: {len(findings)}",
        "",
        "## Risk Findings",
        "",
    ]
    if not findings:
        lines.append("No security findings were identified.")
        lines.append("")
    else:
        for finding in findings:
            lines.extend(
                [
                    f"### {finding.title} ({finding.severity.value})",
                    "",
                    f"- Rule: `{finding.rule_id}`",
                    f"- Location: `{finding.location.path}:{finding.location.start_line}-{finding.location.end_line}`",
                    f"- Evidence: {finding.description}",
                ]
            )
            if finding.cwe:
                lines.append(f"- CWE: {finding.cwe}")
            if finding.cve:
                lines.append(f"- CVE: {finding.cve}")
            policy_refs = [
                item
                for item in policies
                if finding.cwe and finding.cwe.replace("CWE-", "") in item.path
            ] or policies[:1]
            if policy_refs:
                lines.append(
                    f"- Policy citation: `{policy_refs[0].path}` L{policy_refs[0].start_line}"
                )
            lines.append("")

    lines.extend(["## Cited Policies", ""])
    if policies:
        lines.extend(_format_citation(item) for item in policies)
    else:
        lines.append("- None")
    lines.append("")

    lines.extend(["## Cited Code", ""])
    if code:
        lines.extend(_format_citation(item) for item in code)
    else:
        lines.append("- None")
    lines.append("")

    lines.extend(["## Suggested Patch", ""])
    patch_proposals = [item for item in state.proposals if item.kind == "patch"]
    if patch_proposals:
        lines.append(f"- See `{patch_proposals[0].ref}`")
    else:
        lines.append("- No automated patch proposed for this review.")
    lines.append("")

    lines.extend(["## Trace References", ""])
    lines.append(f"- Timeline: `.sac/enterprise/runs/{state.run_id}/timeline.json`")
    for node_name in state.node_outputs:
        lines.append(f"- Node `{node_name}` completed")
    lines.append("")
    return "\n".join(lines)
