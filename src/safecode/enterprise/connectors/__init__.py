"""Enterprise 外部连接器子包。

封装与 GitHub PR、Jira Issue、分支操作等外部系统的只读/受控写集成。
连接器输出标准化证据模型（如 ``PullRequestEvidence``、``IssueEvidence``），
供工作流 ``collect_repo_context`` 与 ``retrieve`` 节点消费。

所有网络写操作须经策略门与审批，连接器本身不绕过安全内核。
"""
