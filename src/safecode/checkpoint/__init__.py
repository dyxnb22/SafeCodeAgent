"""Checkpoint and rollback support.

中文包说明：检查点与回滚子系统。
- 职责：在 patch 应用前备份受影响文件，支持按 ID 或最近一次回滚；备份文件带 sha256 完整性校验。
- 架构位置：与 patch 流程和 FilesystemBoundary 配合，保证文件写入工作流具备可逆补偿路径。
- 与 Enterprise 的关系：Enterprise 运行证据可引用 checkpoint 元数据；回滚仍由内核确定性逻辑执行，不因远程审批而跳过完整性校验。
"""
