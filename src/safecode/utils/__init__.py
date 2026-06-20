"""Shared utility helpers.

中文包说明：跨模块共享工具函数。
- 职责：提供 UTC 时间戳、路径规范化、文件锁等无业务语义的确定性辅助。
- 架构位置：被 audit、task、subagents、shell 等内核模块广泛依赖的基础层。
- 与 Enterprise 的关系：Enterprise 模块复用本层时间与时区约定，保持检查点与审计
  时间戳格式与内核一致。
"""
