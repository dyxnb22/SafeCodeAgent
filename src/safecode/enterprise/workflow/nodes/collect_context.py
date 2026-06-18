"""collect_repo_context node stub."""

from __future__ import annotations

from pathlib import Path

from safecode.enterprise.connectors.github_pr import PullRequestConnectorSpec, fetch_pr
from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.nodes._helpers import build_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.types import TaskType

NODE_NAME = "collect_repo_context"


async def run(state: EnterpriseRunState) -> NodePatch:
    updates: dict = {"missing_evidence": False}
    if state.task_type == TaskType.pr_review and state.request.input_kind == "pr_fixture":
        repo_root = Path(state.repo.repo_root).resolve()
        input_ref = Path(state.request.input_ref)
        if input_ref.is_absolute():
            fixture_path = input_ref.resolve()
            project_root = fixture_path.parent
        else:
            fixture_path = (repo_root / input_ref).resolve()
            project_root = repo_root
        if repo_root not in fixture_path.parents and fixture_path != repo_root:
            raise ValueError("PR fixture path escapes repository root")
        if fixture_path.is_file():
            evidence = fetch_pr(
                PullRequestConnectorSpec(
                    mode="fixture",
                    fixture_path=fixture_path.name,
                    project_root=str(project_root),
                )
            )
            updates["pull_request_evidence"] = evidence
    return build_patch(
        state,
        NODE_NAME,
        summary="collected repository context",
        state_updates=updates,
    )
