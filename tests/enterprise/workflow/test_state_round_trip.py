"""State round-trip and schema tests (v1.2.1-T2)."""

import json

import pytest

from safecode.enterprise.rag.models import Citation
from safecode.enterprise.rag.source_registry import SourceType
from safecode.enterprise.workflow.exceptions import InvalidStateSchemaVersionError
from safecode.enterprise.workflow.state import (
    EnterpriseRunState,
    RBACSubject,
    RepoContext,
    RunRequest,
    STATE_SCHEMA_VERSION,
)
from safecode.enterprise.workflow.types import TaskType, WorkflowStatus


def _sample_state() -> EnterpriseRunState:
    return EnterpriseRunState(
        run_id="run-test123456",
        tenant_id="local",
        task_type=TaskType.pr_review,
        status=WorkflowStatus.pending,
        actor_id="user:test",
        subject=RBACSubject(actor_id="user:test", tenant_id="local"),
        policy_snapshot_id="snapshot-test",
        request=RunRequest(
            task_type=TaskType.pr_review,
            input_kind="pr_fixture",
            input_ref="examples/enterprise/pr_fixture.json",
            actor_id="user:test",
        ),
        repo=RepoContext(repo_root="/tmp/repo"),
        citations=[
            Citation(
                citation_id="cite-1",
                source_id="policy-secure-sql-001",
                source_type=SourceType.security_policy,
                path="policy.md",
                start_line=1,
                end_line=2,
                score=0.9,
                selection_reason="lex=0.5,sem=0.4",
                permission_verdict="allowed",
                freshness="current",
                hash="sha256:abc",
            )
        ],
        created_at="2026-06-19T00:00:00+00:00",
        updated_at="2026-06-19T00:00:00+00:00",
    )


def test_state_json_round_trip_is_lossless():
    state = _sample_state()
    restored = EnterpriseRunState.model_validate_json(state.model_dump_json())
    assert restored == state


def test_state_json_keys_are_stable():
    state = _sample_state()
    first = json.loads(state.model_dump_json())
    second = json.loads(state.model_dump_json())
    assert list(first.keys()) == list(second.keys())


def test_tenant_id_propagates_from_subject():
    state = _sample_state()
    assert state.tenant_id == state.subject.tenant_id


def test_invalid_schema_version_rejected():
    payload = _sample_state().model_dump(mode="python")
    payload["schema_version"] = "0.0.1"
    with pytest.raises(InvalidStateSchemaVersionError):
        EnterpriseRunState.model_validate(payload)


def test_schema_version_default():
    assert _sample_state().schema_version == STATE_SCHEMA_VERSION
