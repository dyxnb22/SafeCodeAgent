"""collect_repo_context 工作流节点（九步流水线第 2 步）。

- **流水线位置**：第 2 步 / 9 — 通过连接器与本地 fixture 收集类型化证据。
- **输入**：已分类的 ``request``（``input_kind``、``input_ref``、``extra``）及
  ``repo.repo_root``。
- **输出**：``findings``、``pull_request_evidence`` 或 ``issue_evidence``；证据缺失时
  置 ``missing_evidence=True``。
- **安全治理**：工具驱动、确定性收集；连接器输出视为不可信输入；不应用补丁、不
  发帖；为后续 RAG 权限过滤提供原始证据边界。
"""

from __future__ import annotations

from pathlib import Path

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks import pr_review, remediation, secure_planning

NODE_NAME = "collect_repo_context"


async def run(state: EnterpriseRunState) -> NodePatch:
    """按任务类型调用 remediation / pr_review / secure_planning 收集器。"""
    updates: dict = {"missing_evidence": False}
    repo_root = Path(state.repo.repo_root).resolve()
    if remediation.is_remediation_task(state) and state.request.input_kind in {
        "finding_fixture",
        "finding_live",
    }:
        try:
            findings = remediation.ingest_findings(repo_root, state.request.input_ref)
        except ValueError:
            raise
        except (FileNotFoundError, OSError):
            findings = []
        if not findings:
            updates["missing_evidence"] = True
        else:
            updates["findings"] = findings
    elif pr_review.is_pr_review_task(state) and state.request.input_kind in {
        "pr_fixture",
        "pr_live",
    }:
        evidence = pr_review.collect_pull_request(
            repo_root,
            state.request.input_ref,
            input_kind=state.request.input_kind,
            extra=state.request.extra,
            installation_id=state.request.extra.get("installation_id"),
        )
        if evidence is None or not evidence.hunks:
            updates["missing_evidence"] = True
        else:
            updates["pull_request_evidence"] = evidence
    elif secure_planning.is_secure_planning_task(state) and state.request.input_kind == "ticket":
        evidence, issue_key = secure_planning.collect_issue(
            repo_root,
            state.request.input_ref,
            input_kind=state.request.input_kind,
            extra=state.request.extra,
        )
        if evidence is None:
            updates["missing_evidence"] = True
        else:
            updates["issue_evidence"] = evidence
            if issue_key and state.request.extra.get("issue_key") is None:
                updates["request"] = state.request.model_copy(
                    update={"extra": {**state.request.extra, "issue_key": issue_key}}
                )
    return build_patch(
        state,
        NODE_NAME,
        summary="collected repository context",
        state_updates=updates,
    )
