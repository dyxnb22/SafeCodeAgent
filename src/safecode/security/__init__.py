"""SafeCode security utilities (keychain, redaction, etc.).

中文包说明：安全工具子模块。
- 职责：密钥链访问、凭证与敏感路径处理等横切安全原语，供 audit、context、config 等复用。
- 架构位置：底层安全设施，不包含业务策略裁决，仅提供安全存储与脱敏能力。
- 与 Enterprise 的关系：Enterprise 身份与密钥管理可对接外部 IdP/保管库；内核 redaction 规则在日志与追踪落盘前仍须生效。
"""
