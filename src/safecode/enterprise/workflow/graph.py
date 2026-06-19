"""LangGraph adapter for enterprise workflows (optional dependency)."""

from __future__ import annotations

from typing import Any, TypedDict

from safecode.enterprise.persistence.local_backend import LocalBackend
from safecode.enterprise.workflow.checkpoint import CHECKPOINT_SCHEMA_VERSION, RunCheckpoint
from safecode.enterprise.workflow.exceptions import LangGraphUnavailableError
from safecode.enterprise.workflow.nodes.registry import NODE_RUNNERS, WORKFLOW_NODE_ORDER
from safecode.enterprise.workflow.orchestrator import LocalOrchestrator
from safecode.enterprise.workflow.patch import apply_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.types import RiskTier, WorkflowStatus

REPAIR_OR_BLOCKER_NODE = "repair_or_blocker"

EXPECTED_WORKFLOW_NODES: tuple[str, ...] = WORKFLOW_NODE_ORDER + (REPAIR_OR_BLOCKER_NODE,)

CONDITIONAL_EDGES: dict[str, tuple[str, str]] = {
    "missing_evidence": ("collect_repo_context", "retrieve_policy_and_code"),
    "high_risk": ("analyze_security_risk", "approval_gate"),
    "validation_failed": ("validate", REPAIR_OR_BLOCKER_NODE),
}


class GraphState(TypedDict):
    enterprise_state: dict[str, Any]


def _import_langgraph():
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise LangGraphUnavailableError(
            "langgraph is not installed; install with the enterprise optional extra"
        ) from exc
    return StateGraph, START, END


def _route_missing_evidence(state: GraphState) -> str:
    current = EnterpriseRunState.model_validate(state["enterprise_state"])
    if current.missing_evidence:
        return "retrieve_policy_and_code"
    return "analyze_security_risk"


def _route_high_risk(state: GraphState) -> str:
    current = EnterpriseRunState.model_validate(state["enterprise_state"])
    if current.risk_tier in {RiskTier.high, RiskTier.critical}:
        return "approval_gate"
    return "plan_actions"


def _route_validation_failed(state: GraphState) -> str:
    current = EnterpriseRunState.model_validate(state["enterprise_state"])
    if current.validation_failed:
        return REPAIR_OR_BLOCKER_NODE
    return "approval_gate"


def _make_node(node_name: str):
    async def _node(state: GraphState) -> GraphState:
        current = EnterpriseRunState.model_validate(state["enterprise_state"])
        patch = await NODE_RUNNERS[node_name](current)
        updated = apply_patch(current, patch)
        return {"enterprise_state": updated.model_dump(mode="python")}

    return _node


def _repair_or_blocker(state: GraphState) -> GraphState:
    current = EnterpriseRunState.model_validate(state["enterprise_state"])
    updated = current.model_copy(
        update={"status": WorkflowStatus.blocked, "updated_at": current.updated_at}
    )
    return {"enterprise_state": updated.model_dump(mode="python")}


def build_state_graph():
    StateGraph, START, END = _import_langgraph()
    graph = StateGraph(GraphState)
    for node_name in WORKFLOW_NODE_ORDER:
        graph.add_node(node_name, _make_node(node_name))
    graph.add_node(REPAIR_OR_BLOCKER_NODE, _repair_or_blocker)
    graph.add_edge(START, WORKFLOW_NODE_ORDER[0])
    graph.add_edge(WORKFLOW_NODE_ORDER[0], WORKFLOW_NODE_ORDER[1])
    graph.add_conditional_edges(WORKFLOW_NODE_ORDER[1], _route_missing_evidence)
    graph.add_edge("retrieve_policy_and_code", WORKFLOW_NODE_ORDER[3])
    graph.add_conditional_edges(WORKFLOW_NODE_ORDER[3], _route_high_risk)
    graph.add_edge("plan_actions", WORKFLOW_NODE_ORDER[5])
    graph.add_edge(WORKFLOW_NODE_ORDER[5], WORKFLOW_NODE_ORDER[6])
    graph.add_conditional_edges(WORKFLOW_NODE_ORDER[6], _route_validation_failed)
    graph.add_edge("approval_gate", WORKFLOW_NODE_ORDER[8])
    graph.add_edge(REPAIR_OR_BLOCKER_NODE, END)
    graph.add_edge(WORKFLOW_NODE_ORDER[8], END)
    return graph.compile()


async def run_langgraph_workflow(
    backend: LocalBackend, state: EnterpriseRunState
) -> EnterpriseRunState:
    compiled = build_state_graph()
    result = await compiled.ainvoke({"enterprise_state": state.model_dump(mode="python")})
    final = EnterpriseRunState.model_validate(result["enterprise_state"])
    backend.runs.save_checkpoint(
        tenant_id=final.tenant_id,
        checkpoint=RunCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            run_id=final.run_id,
            completed_nodes=list(WORKFLOW_NODE_ORDER),
            next_node=None,
            state=final,
        ),
    )
    return final


async def resume_langgraph_workflow(
    backend: LocalBackend, checkpoint: RunCheckpoint
) -> EnterpriseRunState:
    local = LocalOrchestrator(backend.sac_root, runtime="local", backend=backend)
    return await local.resume(checkpoint.run_id, tenant_id=checkpoint.state.tenant_id)
