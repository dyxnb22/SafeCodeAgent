"""Enterprise durable worker package (v2.1.5).

中文说明
--------
持久化 Worker 子包：从命令队列轮询 ``start`` / ``resume`` / ``cancel`` 任务，
在获取运行租约（lease）后调用 ``LocalOrchestrator`` 执行或恢复工作流。
租约防止同一 ``run_id`` 被多个 worker 并发处理；失败任务按重试次数进入 DLQ。
详见 ``runner.WorkerRunner``。
"""

from safecode.enterprise.worker.models import QueueJob, RunAccepted, RunCommandRecord
from safecode.enterprise.worker.queue import CommandQueue, IdempotencyConflictError, LocalCommandQueue

__all__ = [
    "CommandQueue",
    "IdempotencyConflictError",
    "LocalCommandQueue",
    "QueueJob",
    "RunAccepted",
    "RunCommandRecord",
]
