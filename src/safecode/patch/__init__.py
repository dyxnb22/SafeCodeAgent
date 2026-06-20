"""Patch parsing, validation, diffing, and applying.

中文包说明：补丁解析、校验与应用子系统。
- 职责：解析模型或工具产出的 ``PatchProposal``，校验路径与内容边界，生成 diff，
  并在 ``FilesystemBoundary`` 约束下事务性应用或回滚。
- 架构位置：连接 LLM/Agent 补丁提案与 checkpoint 回滚链路的安全写入边界。
- 与 Enterprise 的关系：Enterprise ``propose`` 节点生成本地补丁草稿；``finalize`` 在
  审批消耗后调用本层与 checkpoint 执行受控应用。
"""
