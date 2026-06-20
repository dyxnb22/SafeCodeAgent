"""Project context collection.

中文包说明：项目上下文收集子系统。
- 职责：聚合仓库文件、诊断与预算内上下文片段，并提供密钥/敏感信息脱敏（redactor）。
- 架构位置：为 LLM 与工具提供带来源标识的只读上下文，不赋予执行权限。
- 与 Enterprise 的关系：Enterprise RAG 检索结果须保留 citation 与权限裁决；内核 redactor 在审计与持久化路径上同样适用。
"""
