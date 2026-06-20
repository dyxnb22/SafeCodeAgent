"""Core typed substrates shared across SafeCode subsystems.

中文包说明：跨子系统共享的核心类型基底。
- 职责：Diagnostic 等通用类型与聚合辅助，供 policy 审计、健康检查与 CLI 输出统一结构化。
- 架构位置：最底层共享模型，无 I/O 与策略副作用，避免各子系统重复定义诊断契约。
- 与 Enterprise 的关系：Enterprise 组件可复用 Diagnostic 形态；安全不变量定义在 AGENTS.md 与各领域模块，不在此包放宽。
"""

from safecode.core.diagnostic import (
    Diagnostic,
    DiagnosticGroup,
    DiagnosticStatus,
    aggregate_status,
    all_passed,
)

__all__ = [
    "Diagnostic",
    "DiagnosticGroup",
    "DiagnosticStatus",
    "aggregate_status",
    "all_passed",
]
