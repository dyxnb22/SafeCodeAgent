"""Local Git helpers for experimental SafeCode delivery commands.

中文包说明：本地 Git 操作辅助模块。
- 职责：以 argv 白名单方式封装 status、diff、commit、branch 等本地 git 子命令；
  与审计日志和任务侧车状态联动，输出经密钥脱敏。
- 架构位置：为实验性交付命令提供受控 Git 读写，不替代 Enterprise GitHub 连接器。
- 与 Enterprise 的关系：Enterprise 远程 PR/Issue 写入走 connectors；本包仅服务本地
  内核 CLI 与实验流程，仍受策略与审批约束。
"""
