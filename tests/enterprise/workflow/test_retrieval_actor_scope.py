"""Retrieval actor scope tests."""

from __future__ import annotations

from pathlib import Path

from safecode.enterprise.rbac.models import RBACSubject, Role
from safecode.enterprise.workflow.orchestrator import build_initial_state
from safecode.enterprise.workflow.tasks import pr_review, remediation
from safecode.enterprise.workflow.types import TaskType


def _state(*, roles: tuple[Role, ...], scopes: tuple[str, ...] = ("org",)) -> object:
    state = build_initial_state(
        task_type=TaskType.pr_review,
        input_ref="fixture.json",
        actor_id="user:test",
        repo_root=Path("/tmp/repo"),
        run_id="run-scope00001",
    )
    return state.model_copy(
        update={
            "subject": RBACSubject(
                actor_id="user:test",
                tenant_id=state.tenant_id,
                roles=roles,
                permission_scopes=scopes,
            )
        }
    )


def test_viewer_retrieval_scope_is_org_only() -> None:
    scopes = set(pr_review.retrieval_actor_scope(_state(roles=(Role.viewer,))))
    assert scopes == {"org"}


def test_security_reviewer_retrieval_scope_uses_explicit_subject_scopes() -> None:
    scopes = set(
        remediation.retrieval_actor_scope(
            _state(roles=(Role.security_reviewer,), scopes=("org", "appsec")),
        )
    )
    assert scopes == {"org", "appsec"}


def test_role_does_not_expand_explicit_retrieval_scope() -> None:
    scopes = set(
        remediation.retrieval_actor_scope(
            _state(roles=(Role.platform_admin,), scopes=("org",)),
        )
    )
    assert scopes == {"org"}
