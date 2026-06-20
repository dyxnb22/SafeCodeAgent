"""工作流节点注册表与规范执行顺序。

节点顺序（共 9 步）：
1. classify_request      — 分类任务类型与输入
2. collect_repo_context  — 收集仓库/PR/Issue 上下文
3. retrieve_policy_and_code — RAG 检索策略与代码证据
4. analyze_security_risk — 安全分析与风险定级
5. plan_actions          — 生成修复/审查计划
6. propose_report_or_patch — 产出报告或补丁提案
7. validate              — 校验提案（测试、策略一致性）
8. approval_gate         — 高风险人审门（可中断）
9. finalize              — 落盘报告、审计锚点、终态

编排器与 worker 均通过 ``NODE_RUNNERS`` 按名派发，禁止绕过注册表直接调用节点模块。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes import (
    analyze,
    approval,
    classify,
    collect_context,
    finalize,
    plan,
    propose,
    retrieve,
    validate,
)
from safecode.enterprise.workflow.state import EnterpriseRunState

WORKFLOW_NODE_ORDER: tuple[str, ...] = (
    # 顺序即检查点恢复时的遍历次序；修改顺序需同步迁移 schema 与测试
    "classify_request",
    "collect_repo_context",
    "retrieve_policy_and_code",
    "analyze_security_risk",
    "plan_actions",
    "propose_report_or_patch",
    "validate",
    "approval_gate",
    "finalize",
)

NODE_RUNNERS: dict[str, Callable[[EnterpriseRunState], Awaitable[NodePatch]]] = {
    "classify_request": classify.run,
    "collect_repo_context": collect_context.run,
    "retrieve_policy_and_code": retrieve.run,
    "analyze_security_risk": analyze.run,
    "plan_actions": plan.run,
    "propose_report_or_patch": propose.run,
    "validate": validate.run,
    "approval_gate": approval.run,
    "finalize": finalize.run,
}
