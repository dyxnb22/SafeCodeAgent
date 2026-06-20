"""Node patch immutability tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.enterprise.workflow.contracts import NodePatch
from safecode.enterprise.workflow.exceptions import InvalidStateUpdateError
from safecode.enterprise.workflow.orchestrator import build_initial_state
from safecode.enterprise.workflow.patch import apply_patch
from safecode.enterprise.workflow.state import EnterpriseRunState
from safecode.enterprise.workflow.types import TaskType


@pytest.fixture
def base_state(tmp_path: Path) -> EnterpriseRunState:
    return build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=tmp_path,
        run_id="run-patch00001",
    )


def test_node_cannot_overwrite_actor_id(base_state: EnterpriseRunState) -> None:
    patch = NodePatch(
        node_name="test",
        status="ok",
        state_updates={"actor_id": "attacker"},
    )
    with pytest.raises(InvalidStateUpdateError, match="immutable"):
        apply_patch(base_state, patch)


def test_node_cannot_overwrite_tenant_id(base_state: EnterpriseRunState) -> None:
    patch = NodePatch(
        node_name="test",
        status="ok",
        state_updates={"tenant_id": "attacker-tenant"},
    )
    with pytest.raises(InvalidStateUpdateError, match="immutable"):
        apply_patch(base_state, patch)


def test_node_cannot_overwrite_request_identity(base_state: EnterpriseRunState) -> None:
    patch = NodePatch(
        node_name="test",
        status="ok",
        state_updates={
            "request": base_state.request.model_copy(update={"input_ref": "other.json"})
        },
    )
    with pytest.raises(InvalidStateUpdateError, match="request identity"):
        apply_patch(base_state, patch)
