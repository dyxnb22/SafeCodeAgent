"""Workflow node registry and canonical ordering."""

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
