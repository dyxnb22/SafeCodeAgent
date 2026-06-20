"""Shell execution, policy, and interactive runtime primitives.

中文包说明：Shell 命令执行与交互运行时。
- 职责：通过 ``ShellRunner`` 在命令策略、沙箱文件系统与网络策略下执行命令；
  提供风险分级、会话管理与 CLI 渲染；hooks 子模块复用本层执行项目钩子。
- 架构位置：内核工具链中所有命令执行的唯一受控入口，位于 policy 裁决之后。
- 与 Enterprise 的关系：Enterprise 扫描器与沙箱生命周期复用本层策略语义；高风险
  命令须人工审批，模型输出不得直接绕过 ``CommandPolicy``。
"""
