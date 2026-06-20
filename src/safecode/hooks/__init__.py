"""Project hooks.

中文包说明：项目级钩子执行模块。
- 职责：读取项目配置的 pre/post 钩子，经 ``ShellRunner`` 与 ``HookApprovalStore``
  在策略门控下执行；测试类命令可自动识别。
- 架构位置：位于 shell 执行层之上，为工作流 validate 与本地 CI 集成提供扩展点。
- 与 Enterprise 的关系：Enterprise validate 节点可触发扫描器；项目钩子仍须通过内核
  审批与审计，不得削弱 Enterprise 策略快照约束。
"""
