"""Unified policy engines.

中文包说明：统一策略引擎（本地内核）。
- 职责：命令 allowlist、参数级风险检测、策略预设审计与 diff；对 shell/hooks 等执行路径给出允许/拒绝/需审批结论。
- 架构位置：位于配置（SafeCodeConfig）与 shell/sandbox 执行之间，是本地模式的确定性策略裁决层。
- 与 Enterprise 的关系：Enterprise 有独立多层 PolicyResolver（org/user/project 等）；本地内核 CommandPolicy 与 preset 审计仍用于 CLI 与本地沙箱，二者互补，项目配置不得弱化组织策略。
"""
