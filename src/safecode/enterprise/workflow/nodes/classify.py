"""classify_request 工作流节点（九步流水线第 1 步）。

- **流水线位置**：第 1 步 / 9 — 将 ``RunRequest`` 规范化为可执行子图输入。
- **输入**：``EnterpriseRunState.request``（任务类型、``input_ref``、``extra``）。
- **输出**：``NodePatch``，更新 ``status``、``missing_evidence``；对 GitHub Webhook
  载荷解析 ``owner`` / ``repo`` / ``pr_number`` 并设置 ``input_kind``（``pr_live`` 或
  ``finding_live``）。
- **安全治理**：纯确定性节点，不调用模型；不执行写入或外部连接器调用；为后续
  RAG 与审批门提供经类型约束的任务上下文。
"""

from __future__ import annotations

import json

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks import pr_review
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus

NODE_NAME = "classify_request"


def parse_github_webhook_input(input_ref: str) -> dict[str, str] | None:
    """解析 GitHub Webhook JSON 载荷，提取仓库与 PR 元数据。

    仅接受 ``source=github_webhook`` 且包含合法 ``owner/repo`` 与 ``pr_number`` 的
    载荷；解析失败返回 ``None``，调用方保持原有 ``input_kind`` 不变。
    """
    try:
        payload = json.loads(input_ref)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("source") != "github_webhook":
        return None
    repo = str(payload.get("repo") or "").strip()
    if "/" not in repo:
        return None
    owner, repo_name = repo.split("/", 1)
    pr_number = str(payload.get("pr_number") or "").strip()
    if not owner or not repo_name or not pr_number:
        return None
    extra = {
        "owner": owner,
        "repo": repo_name,
        "pr_number": pr_number,
        "delivery_id": str(payload.get("delivery_id") or ""),
        "webhook_action": str(payload.get("action") or ""),
    }
    return extra


async def run(state: EnterpriseRunState) -> NodePatch:
    """执行分类节点：标记运行中并按任务类型规范化 Webhook 输入。"""
    updates: dict = {
        "status": WorkflowStatus.running,
        "missing_evidence": False,
    }
    if state.task_type is TaskType.pr_review:
        webhook_extra = parse_github_webhook_input(state.request.input_ref)
        if webhook_extra is not None:
            updates["request"] = state.request.model_copy(
                update={
                    "input_kind": "pr_live",
                    "extra": {**state.request.extra, **webhook_extra},
                }
            )
    elif state.task_type is TaskType.remediation:
        webhook_extra = parse_github_webhook_input(state.request.input_ref)
        if webhook_extra is not None:
            updates["request"] = state.request.model_copy(
                update={
                    "input_kind": "finding_live",
                    "extra": {**state.request.extra, **webhook_extra},
                }
            )
    return build_patch(
        state,
        NODE_NAME,
        summary=f"classified task {state.task_type.value}",
        state_updates=updates,
    )
