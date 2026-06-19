"""classify_request node."""

from __future__ import annotations

import json

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.tasks import pr_review
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus

NODE_NAME = "classify_request"


def parse_github_webhook_input(input_ref: str) -> dict[str, str] | None:
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
