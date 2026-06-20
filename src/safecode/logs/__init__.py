"""Runtime logging.

中文包说明：结构化运行时日志模块。
- 职责：将组件级事件写入 ``.sac/logs/runtime.jsonl``，自动脱敏密钥并标注失败分类。
- 架构位置：面向调试与故障诊断的旁路日志，补充 audit 哈希链而非替代之。
- 与 Enterprise 的关系：Enterprise 审计走 ``enterprise.audit`` 与工具调用记录；
  本模块服务内核 shell/agent 运行时，日志内容在持久化前经同一脱敏规则处理。
"""
