"""Trace events and performance budgets.

中文包说明：追踪事件与性能预算模块。
- 职责：定义 ``PerformanceBudget`` 及上下文大小、磁盘增长等确定性计量辅助函数；
  为 eval/replay 运行提供轻量遥测，不引入额外运行时依赖。
- 架构位置：可观测性内核，与 audit 哈希链互补；Enterprise 有独立的 trace 子包。
- 与 Enterprise 的关系：Enterprise 工作流节点通过 ``TraceEventDraft`` 写入运行时间线；
  本包提供 replay/eval 场景的预算模型，不替代 Enterprise 审计事件。
"""

from safecode.trace.budget import (
    PerformanceBudget,
    compute_context_size,
    compute_disk_growth,
)

__all__ = ["PerformanceBudget", "compute_context_size", "compute_disk_growth"]
