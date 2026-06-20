"""Tool registry.

中文包说明：工具注册与门控子系统。
- 职责：注册工具规格（风险、审批类别、审计事件），经 ToolCallGate 在副作用前做 fail-closed 校验。
- 架构位置：所有写文件、执行命令、MCP 写操作等须经 registry + gate，模型不能直接调用未注册工具。
- 与 Enterprise 的关系：Enterprise 扩展 connector/扫描器等工具规格；未知工具默认拒绝，审批状态须由人类或显式批准流程传入，不能由 Agent 自批。
"""
