"""LangGraph 企业工作流适配层（可选依赖）。

将 ``WORKFLOW_NODE_ORDER`` 中的节点注册为 LangGraph 状态图，并在三处引入条件边：
- ``collect_repo_context`` 之后：缺证据则补检索，否则直接分析
- ``analyze_security_risk`` 之后：高/极高风险走审批门，否则直接规划
- ``validate`` 之后：校验失败进入 ``repair_or_blocker`` 终止为 blocked

与本地编排器的差异：本地模式始终线性执行全部 9 个节点；LangGraph 可跳过
``retrieve_policy_and_code`` 或 ``approval_gate``。恢复时 ``resume_langgraph_workflow``
实际委托给 ``LocalOrchestrator.resume``，并非 LangGraph 原生 checkpoint 恢复。

潜在问题：
- ``run_langgraph_workflow`` 结束时将 ``completed_nodes`` 固定为全部节点，即使图中途结束
- 未安装 langgraph 时抛出 ``LangGraphUnavailableError``
"""

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
    # 路由名 -> (条件为真时的目标, 条件为假时的目标) — 仅作文档索引，实际路由在下方函数中
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
    """缺证据时补检索，否则跳过 retrieve 直接分析风险。"""
    current = EnterpriseRunState.model_validate(state["enterprise_state"])
    if current.missing_evidence:
        return "retrieve_policy_and_code"
    return "analyze_security_risk"


def _route_high_risk(state: GraphState) -> str:
    """高/极高风险必须经过 approval_gate，低风险可跳过审批直接 finalize 路径。"""
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
    """构建并编译 LangGraph 状态图。节点顺序与 registry.WORKFLOW_NODE_ORDER 对齐。"""
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
    """一次性执行完整 LangGraph 图，结束后写检查点。

    注意：无论实际经过哪些节点，completed_nodes 均记为全部 WORKFLOW_NODE_ORDER。
    """
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
    """LangGraph 模式的恢复入口 — 实际回落到本地编排器 resume，非图内断点续跑。"""
    local = LocalOrchestrator(backend.sac_root, runtime="local", backend=backend)
    return await local.resume(checkpoint.run_id, tenant_id=checkpoint.state.tenant_id)
