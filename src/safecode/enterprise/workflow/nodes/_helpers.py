"""工作流节点共享辅助函数。

为九个规范节点提供统一的 ``NodePatch`` 构造、UTC 时间戳与追踪事件草稿生成。
所有节点通过 ``build_patch`` 写入 ``node_outputs`` 与 ``TraceEventDraft``，保证
检查点序列化与审计时间线格式一致；不包含业务逻辑或策略裁决。
"""

from __future__ import annotations

from datetime import datetime, timezone

from safecode.enterprise.workflow.contracts import NodeCost, NodePatch, NodeOutput, TraceEventDraft
from safecode.enterprise.workflow.state import EnterpriseRunState


def utc_now_iso() -> str:
    """返回不含微秒的 UTC ISO-8601 时间戳字符串。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def trace_event(state: EnterpriseRunState, node_name: str, kind: str = "node.end") -> TraceEventDraft:
    """构造节点级追踪事件草稿，供 ``NodePatch.events`` 与审计链路消费。"""
    return TraceEventDraft(
        event_id=f"{state.run_id}:{node_name}:{kind}",
        kind=kind,
        payload={"run_id": state.run_id, "node_name": node_name, "tenant_id": state.tenant_id},
    )


def build_patch(
    state: EnterpriseRunState,
    node_name: str,
    *,
    summary: str,
    state_updates: dict | None = None,
    status: str = "ok",
) -> NodePatch:
    """将节点执行摘要、状态增量与追踪事件封装为统一的 ``NodePatch``。"""
    updates = dict(state_updates or {})
    node_outputs = dict(state.node_outputs)
    node_outputs[node_name] = NodeOutput(
        node_name=node_name,
        status=status,
        summary=summary,
        started_at=state.updated_at,
        ended_at=utc_now_iso(),
    )
    updates["node_outputs"] = node_outputs
    updates["updated_at"] = utc_now_iso()
    return NodePatch(
        node_name=node_name,
        status=status,
        state_updates=updates,
        events=[trace_event(state, node_name)],
        cost=NodeCost(latency_ms=1, request_count=1),
        duration_ms=1,
    )
