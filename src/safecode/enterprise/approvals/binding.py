"""Deterministic workflow action bindings for human approvals.

将工作流运行状态绑定到待审批的 Action 与 target 快照。
核心不变量：审批授权仅覆盖绑定时刻的 proposal 内容（含 sha256），
后续 proposal 变更须重新发起审批；模型生成的 proposal 本身无执行权威。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from safecode.enterprise.approvals.store import Action
from safecode.enterprise.connectors.github_pr_write import comment_approval_target
from safecode.enterprise.connectors.jira_live import comment_approval_target as jira_comment_approval_target
from safecode.enterprise.workflow.state import EnterpriseRunState, Proposal
from safecode.enterprise.workflow.types import TaskType


def _proposal_digest(proposal: Proposal | None) -> str:
    """计算 proposal 引用文件的 SHA-256，用于检测审批后内容被篡改。

    潜在问题：proposal.ref 指向的文件不存在时返回空串，调用方须将空摘要视为绑定不完整。
    """
    if proposal is None:
        return ""
    path = Path(proposal.ref)
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workflow_approval_binding(state: EnterpriseRunState) -> tuple[Action, dict[str, str]]:
    """将运行状态绑定到待审批 Action 与 target 字典。

    按 task_type 选择 proposal 种类并构造连接器级 target（如 PR 评论、工单评论）。
    返回的 target 含 proposal_id / proposal_ref / proposal_sha256，执行前须与 grant 逐项比对。

    潜在问题：
    - pr_live 分支在 owner/repo/pr_number 缺失时回退到仅含 proposal 元数据的 target，
      可能导致连接器 target 不完整却仍进入审批流。
    - 默认分支取首个 proposal，多 proposal 并存时可能绑定非预期项。
    """
    proposal: Proposal | None = None
    if state.task_type == TaskType.remediation:
        action = Action.file_write
        proposal = next((item for item in state.proposals if item.kind == "patch"), None)
    elif state.task_type == TaskType.pr_review and state.request.input_kind == "pr_live":
        action = Action.github_write_comment
        proposal = next((item for item in state.proposals if item.kind == "comment"), None)
        if proposal is not None and proposal.ref:
            body = Path(proposal.ref).read_text(encoding="utf-8")
            owner = state.request.extra.get("owner", "")
            repo = state.request.extra.get("repo", "")
            try:
                pr_number = int(state.request.extra.get("pr_number") or 0)
            except ValueError:
                pr_number = 0
            if owner and repo and pr_number > 0:
                return action, comment_approval_target(
                    owner=owner,
                    repo=repo,
                    pr_number=pr_number,
                    body=body,
                )
    elif state.task_type == TaskType.secure_planning and state.request.extra.get("post_to_ticket") == "1":
        action = Action.issue_comment
        proposal = next((item for item in state.proposals if item.kind == "ticket"), None)
        if proposal is not None and proposal.ref:
            body = Path(proposal.ref).read_text(encoding="utf-8")
            issue_key = state.request.extra.get("issue_key", "")
            if issue_key:
                return action, jira_comment_approval_target(issue_key=issue_key, body=body)
    else:
        action = Action.file_write
        proposal = next(iter(state.proposals), None)
    return action, {
        "proposal_id": proposal.proposal_id if proposal else "",
        "proposal_ref": proposal.ref if proposal else "",
        "proposal_sha256": _proposal_digest(proposal),
    }
