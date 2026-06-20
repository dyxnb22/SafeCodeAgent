"""Enterprise governed long-term memory.

中文包说明：受治理的长期记忆子系统。
- 记忆事实须经审批（memory_fact_inject）方可注入上下文；未批准事实默认阻断。
- 写入前脱敏；租户边界与来源标识须保留。
"""

from safecode.enterprise.memory.models import MemoryFact, MemoryFactStatus
from safecode.enterprise.memory.store import MemoryFactStore, MemoryGovernanceError

__all__ = [
    "MemoryFact",
    "MemoryFactStatus",
    "MemoryFactStore",
    "MemoryGovernanceError",
]
