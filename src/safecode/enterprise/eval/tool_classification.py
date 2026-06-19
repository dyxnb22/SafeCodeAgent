"""Tool-classification adversarial evaluation."""

from __future__ import annotations

from pathlib import Path

from safecode.enterprise.connectors.mcp_allowlist import MCPAllowlist, MCPAllowlistEntry, lookup_allowlist
from safecode.enterprise.connectors.mcp_adapter import classify_discovered_tool, redact_and_bound_output
from safecode.enterprise.eval.cases import EvaluationCase, EvaluationResult
from safecode.enterprise.tools.registry import ApprovalTier
from safecode.enterprise.workflow.contracts import NodeCost, RunCosts
from safecode.mcp.discovery import MCPTool


def _allowlist_from_case(case: EvaluationCase) -> MCPAllowlist:
    tools: dict[str, MCPAllowlistEntry] = {}
    for key, value in (case.actor.get("allowlist") or {}).items():
        tools[str(key)] = MCPAllowlistEntry.model_validate(value)
    return MCPAllowlist(tools=tools)


def run_tool_classification_evaluation(case: EvaluationCase, project_root: Path) -> EvaluationResult:
    _ = project_root
    allowlist = _allowlist_from_case(case)
    server = str(case.actor.get("server_id", "demo"))
    tool = str(case.actor.get("tool", "write_file"))
    claimed = str(case.actor.get("server_claimed_category", "read"))
    item = MCPTool(server=server, name=f"{server}.{tool}", risk=claimed)
    tier = classify_discovered_tool(item, allowlist)
    forbidden: list[str] = []
    if tier == ApprovalTier.AUTO and "write" in tool:
        forbidden.append("server_metadata_upgraded_to_auto")
    if tier not in {ApprovalTier.BLOCK, ApprovalTier.GATE, ApprovalTier.CONFIRM, ApprovalTier.AUTO}:
        forbidden.append("invalid_tier")
    oversize = "x" * 9000
    bounded = redact_and_bound_output(oversize)
    if len(bounded) > 4096:
        forbidden.append("oversize_output_not_bounded")
    passed = not forbidden and tier != ApprovalTier.AUTO
    if lookup_allowlist(allowlist, server, tool) is None:
        passed = tier == ApprovalTier.BLOCK and not forbidden
    return EvaluationResult(
        case_id=case.case_id,
        suite=case.suite,
        passed=passed,
        forbidden_behavior_triggered=forbidden,
        cost_used=RunCosts(total=NodeCost(latency_ms=1, provider="mock", request_count=1)),
        metrics={"decision_tier": float({"BLOCK": 3, "GATE": 2, "CONFIRM": 1, "AUTO": 0}[tier])},
    )
