"""Lightweight local memory.

中文包说明：轻量本地记忆子系统。
- 职责：经审批后可注入的本地事实/上下文片段存储，供后续轮次检索；须带来源与权限边界。
- 架构位置：位于 context/RAG 与 Agent 循环之间，避免将未审核模型输出直接持久化为记忆。
- 与 Enterprise 的关系：Enterprise RAG/记忆扩展多租户与检索权限；内核要求记忆注入须经 gate 批准且内容脱敏后方可持久化。
"""
