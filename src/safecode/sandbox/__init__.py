"""Sandbox and containment helpers.

中文包说明：沙箱与隔离辅助模块。
- 职责：文件系统边界、网络策略、沙箱生命周期与工厂适配，限制命令与文件操作在项目范围内。
- 架构位置：与 policy/commands 及 config 中的 sandbox 旋钮联动，在执行层落实 containment。
- 与 Enterprise 的关系：Enterprise 可有独立 enterprise.sandbox 适配；本地 restrict_to_project_root 与 network 默认拒绝等预设不变量须在所有模式下成立。
"""
