"""retrieve_policy_and_code 工作流节点（九步流水线第 3 步）。

- **流水线位置**：第 3 步 / 9 — 在 actor 权限范围内执行混合 RAG 检索。
- **输入**：上一步产出的 ``findings``、``pull_request_evidence`` 或 ``issue_evidence``。
- **输出**：带溯源的 ``citations`` 列表；无引用时 ``missing_evidence=True``。
- **安全治理**：检索结果经权限过滤与引用签名；文档与代码片段为不可信输入，仅供
  分析与计划引用，不直接驱动写入；遵守租户与 RBAC 边界。
"""

from __future__ import annotations

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks import pr_review, remediation, secure_planning

NODE_NAME = "retrieve_policy_and_code"


async def run(state: EnterpriseRunState) -> NodePatch:
    """按任务类型检索策略文档与代码引用，写入 ``citations``。"""
    updates: dict = {}
    if remediation.is_remediation_task(state) and state.findings:
        citations = remediation.retrieve_citations(state, state.findings)
        updates["citations"] = citations
        updates["missing_evidence"] = len(citations) == 0
    elif pr_review.is_pr_review_task(state) and state.pull_request_evidence is not None:
        citations = pr_review.retrieve_citations(state, state.pull_request_evidence)
        updates["citations"] = citations
        updates["missing_evidence"] = len(citations) == 0
    elif secure_planning.is_secure_planning_task(state) and state.issue_evidence is not None:
        citations = secure_planning.retrieve_citations(state, state.issue_evidence)
        updates["citations"] = citations
        updates["missing_evidence"] = len(citations) == 0
    else:
        missing = len(state.citations) == 0
        updates["missing_evidence"] = missing
    return build_patch(
        state,
        NODE_NAME,
        summary="retrieved policy and code citations",
        state_updates=updates,
    )
