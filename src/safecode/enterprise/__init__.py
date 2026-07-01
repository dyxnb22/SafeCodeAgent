"""SafeCodeAgent Enterprise 顶层包。

本包在已完成的安全内核（policy gate、checkpoint、audit、approval）之上，
提供企业级安全工程代理平台能力，主要包括：

- **workflow**：有状态工作流编排（本地顺序执行或可选 LangGraph 适配）
- **worker**：持久化命令队列与租约保护的异步执行器
- **api**：Team Server HTTP 入口（runs、approvals、evidence 等）
- **persistence**：本地文件或 Postgres 后端，统一租户边界与检查点存储
- **auth / rbac**：OIDC 令牌校验与主体映射
- **connectors**：GitHub PR、Jira 等外部系统集成

安全不变量：模型输出不具执行权限；所有写操作须经策略门与人审批准。

**推荐阅读顺序（学习/面试）：**
1. ``workflow/orchestrator.py`` + ``workflow/nodes/`` — 九节点业务流
2. ``rag/retriever.py`` — 权限感知检索
3. ``approvals/store.py`` + ``workflow/nodes/approval.py`` — 人机协同
4. ``policy/resolver.py`` — 策略 precedence
5. ``api/routes/runs.py`` + ``worker/commands.py`` — Team Server 路径
6. ``evidence/export.py`` + ``audit/chain.py`` — 审计与合规导出
"""
