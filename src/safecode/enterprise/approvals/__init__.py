"""Enterprise human approval workflow.

中文包说明：企业级人工审批子系统。
- 模型输出仅为提案（proposal），不具备执行权威；所有写操作、命令、连接器写入须经审批门控。
- 审批请求绑定 proposal 快照（proposal_id / ref / sha256）与策略快照（policy_snapshot_id），
  执行前须逐项校验，快照变更则授权失效。
- 模型主体（model:*）不得批准自身请求；授权（grant）单次消费。
"""
