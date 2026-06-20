"""Enterprise 工作流子包。

工作流按固定节点顺序推进（见 ``nodes.registry.WORKFLOW_NODE_ORDER``），
每个节点产出 ``NodePatch`` 增量更新 ``EnterpriseRunState``，并在节点结束后
持久化检查点（``RunCheckpoint``），以支持审批中断后的恢复。

核心组件：
- ``orchestrator.LocalOrchestrator``：本地顺序编排器，负责 trace 发射与审批暂停
- ``graph``：可选 LangGraph 适配层，在部分节点引入条件分支
- ``state``：Pydantic 状态模型，序列化后写入 ``state.json``
- ``checkpoint``：检查点读写与 GC

运行时由环境变量 ``WORKFLOW_RUNTIME`` 选择 ``local``（默认）或 ``langgraph``。
"""
