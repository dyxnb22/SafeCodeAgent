"""Enterprise public contracts package.

中文包说明：企业对外公共契约（快照 schema）。
- 定义跨模块/API 的稳定数据结构，供集成方与回归测试引用。
- 契约变更须与实现及测试同步，不得静默削弱安全字段。
"""

from safecode.enterprise.contracts.snapshot import all_contracts

__all__ = ["all_contracts"]
