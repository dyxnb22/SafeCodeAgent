"""Evaluation helpers.

中文包说明：评估与回归夹具子系统。
- 职责：提供确定性 eval 辅助与夹具，验证策略门、审计、回滚等安全行为是否符合预期。
- 架构位置：测试与 CI 侧能力，不依赖在线模型或外网，保证内核回归可重复。
- 与 Enterprise 的关系：Enterprise 有独立 enterprise.eval 与验收场景；内核 eval 覆盖共享安全契约，Enterprise 扩展不得削弱既有负向用例。
"""
