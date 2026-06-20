"""SafeCode Agent package.

中文包说明：SafeCodeAgent 安全内核顶层包。
- 职责：对外暴露内核版本号，作为本地安全工程 Agent 的根命名空间。
- 架构位置：Enterprise 平台复用本包中的 policy、audit、checkpoint、tools 等子系统；
  Enterprise 层（`safecode.enterprise`）在其上叠加租户、RBAC、工作流与 Team Server，不得削弱内核不变量。
- 与 Enterprise 的关系：内核提供确定性策略门、审计链、回滚与工具门控；Enterprise 通过适配器调用内核能力，不替代执行裁决权。
"""

__version__ = "7.1.5"
