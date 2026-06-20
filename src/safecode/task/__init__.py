"""Task sidecar state for SafeCode Agent (experimental, v4.1+).

中文包说明：任务侧车状态管理（实验性，v4.1+）。
- 职责：在 ``.sac/tasks/<task_id>.json`` 持久化 ``TaskState``（命令历史、补丁引用、
  审计追踪 ID）；支持预算、恢复与线路连接。
- 架构位置：为长时间运行的 Agent 会话提供可恢复侧车，不修改核心审计 schema。
- 与 Enterprise 的关系：Enterprise 以 ``EnterpriseRunState`` 与检查点为权威状态；
  本侧车服务内核 CLI 实验，与 Enterprise 运行存储相互独立。
"""
