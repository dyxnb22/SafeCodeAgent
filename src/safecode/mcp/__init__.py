"""MCP integration placeholders with real config/discovery flow.

中文包说明：MCP（Model Context Protocol）集成层。
- 职责：MCP 服务发现、配置加载与提案/审批流程占位，将远程能力纳入与本地工具一致的门控模型。
- 架构位置：位于外部 MCP 服务器与内核工具门之间；MCP 读写须分类并默认从严。
- 与 Enterprise 的关系：Enterprise 可挂载租户级 MCP 配置；内核不变量：MCP 响应为不可信输入，写操作须经审批与审计，未知操作默认拒绝。
"""
