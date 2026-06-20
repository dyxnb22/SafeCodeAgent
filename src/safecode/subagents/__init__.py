"""Subagent task model.

中文包说明：子 Agent 任务模型与执行框架。
- 职责：定义 ``SubagentTask`` 生命周期、角色分工、合并策略与文件-backed 执行器；
  限制 task_id 字符集以防目录逃逸。
- 架构位置：内核多 Agent 并行实验层，将父 Agent 目标拆分为可审计的子任务。
- 与 Enterprise 的关系：Enterprise 工作流以规范九节点编排为主；子 Agent 池为内核
  扩展能力，子任务输出仍为不可信提案，须经策略与审批门方可执行写入。
"""
