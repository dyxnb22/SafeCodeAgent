"""Local task queue.

中文包说明：本地文件-backed 任务队列（实验性）。
- 职责：在 ``.sac/queue.json`` 中持久化待处理任务列表，支持增删与状态更新。
- 架构位置：v1.1 实验性本地排队，非 Enterprise Team Server 作业队列。
- 与 Enterprise 的关系：Enterprise worker 使用 persistence 层租约与运行存储；本队列
  仅供内核 CLI 实验，与租户隔离的工作流编排相互独立。
"""
