"""Tests for v4.11.0 typed step model on existing AgentLoop.

Verifies that:
- AgentLoop computes TypedAgentStep/TypedAgentStepResult on every step path.
- Approval-required kinds are flagged correctly.
- model_output_invalid after bounded retry produces the expected classification.
- Typed projection does NOT alter existing AgentLoop.step/run return contracts.
- No mutating kind is auto-approved.

All surfaces under test are EXPERIMENTAL.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.loop import AgentLoop, AgentStepResult, AgentRunResult
from safecode.agent.step_model import (
    AgentStepKind,
    AgentStepStatus,
    TypedAgentStep,
    TypedAgentStepResult,
    APPROVAL_REQUIRED_KINDS,
    READ_ONLY_AUTO_APPROVABLE_KINDS,
    classify_step_from_pending_action,
)
from safecode.agent.schemas import (
    AgentStopForUserResponse,
    AgentToolIntentResponse,
    RecoverableContractFailure,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loop(tmp_path: Path, llm_client: object) -> AgentLoop:
    loop = AgentLoop(project_root=tmp_path, llm_client=llm_client)
    return loop


def _mock_plan_client(steps: list[str] | None = None):
    """Return a mock LLM client that produces a deterministic plan + ask intent."""
    from safecode.agent.schemas import AgentPlanResponse, ToolIntent as SchemaToolIntent, AgentToolIntentResponse
    from safecode.llm.mock import MockLLMClient

    client = MockLLMClient()
    return client


def _mock_client_with_response(response: object) -> MagicMock:
    """Return a mock LLM client whose choose_tool always returns response."""
    client = MagicMock()
    client.plan.return_value = MagicMock(steps=["step one", "step two"])
    client.choose_tool.return_value = response
    return client


def _ask_intent_response() -> AgentToolIntentResponse:
    from safecode.agent.schemas import AgentToolIntentResponse, ToolIntent as SchemaToolIntent
    intent = SchemaToolIntent(type="read", target="README.md", description="read readme")
    return AgentToolIntentResponse(intent=intent)


def _stop_response() -> AgentStopForUserResponse:
    return AgentStopForUserResponse(
        reason="need_input",
        message="Need user input.",
        requires_approval=True,
    )


def _contract_failure() -> RecoverableContractFailure:
    return RecoverableContractFailure(step=0, method="choose_tool", message="bad json")


# ---------------------------------------------------------------------------
# Approval-required kinds invariant
# ---------------------------------------------------------------------------


class TestApprovalRequiredKinds:
    def test_edit_requires_approval(self):
        assert "edit" in APPROVAL_REQUIRED_KINDS

    def test_apply_requires_approval(self):
        assert "apply" in APPROVAL_REQUIRED_KINDS

    def test_run_requires_approval(self):
        assert "run" in APPROVAL_REQUIRED_KINDS

    def test_fix_requires_approval(self):
        assert "fix" in APPROVAL_REQUIRED_KINDS

    def test_commit_requires_approval(self):
        assert "commit" in APPROVAL_REQUIRED_KINDS

    def test_rollback_requires_approval(self):
        assert "rollback" in APPROVAL_REQUIRED_KINDS

    def test_ask_not_approval_required(self):
        assert "ask" not in APPROVAL_REQUIRED_KINDS

    def test_mcp_call_not_approval_required(self):
        assert "mcp_call" not in APPROVAL_REQUIRED_KINDS

    def test_subagent_dispatch_not_approval_required(self):
        assert "subagent_dispatch" not in APPROVAL_REQUIRED_KINDS

    def test_stop_not_approval_required(self):
        assert "stop" not in APPROVAL_REQUIRED_KINDS


# ---------------------------------------------------------------------------
# No mutating kind is auto-approvable via read-only path
# ---------------------------------------------------------------------------


class TestReadOnlyAutoApprovable:
    def test_only_ask_is_auto_approvable(self):
        assert READ_ONLY_AUTO_APPROVABLE_KINDS == frozenset({"ask"})

    @pytest.mark.parametrize("kind", ["edit", "apply", "run", "fix", "commit", "rollback"])
    def test_mutating_kinds_not_auto_approvable(self, kind):
        assert kind not in READ_ONLY_AUTO_APPROVABLE_KINDS

    @pytest.mark.parametrize("kind", ["edit", "apply", "run", "fix", "commit", "rollback"])
    def test_typed_step_from_route_marks_approval_required(self, kind):
        step = TypedAgentStep.from_route(index=0, kind=kind, description="test")
        assert step.requires_approval is True

    def test_ask_step_does_not_require_approval(self):
        step = TypedAgentStep.from_route(index=0, kind="ask", description="read")
        assert step.requires_approval is False


# ---------------------------------------------------------------------------
# classify_step_from_pending_action — pure classifier
# ---------------------------------------------------------------------------


class TestClassifyStepFromPendingAction:
    def test_patch_propose_classifies_as_edit(self):
        action = {"type": "patch", "route": "patch.propose", "requires_approval": True}
        step, result = classify_step_from_pending_action(
            step_index=1, pending_action=action, observation="patch proposed",
            stopped_for_approval=True
        )
        assert step.kind == "edit"
        assert step.requires_approval is True
        assert result.status == "waiting_for_user"

    def test_stop_for_user_classifies_as_stop(self):
        action = {"type": "stop_for_user", "reason": "need_input", "message": "help"}
        step, result = classify_step_from_pending_action(
            step_index=2, pending_action=action, observation="stopped",
            stopped_for_approval=True
        )
        assert step.kind == "stop"
        assert result.status == "waiting_for_user"

    def test_mcp_readonly_classifies_as_mcp_call(self):
        action = {"type": "mcp", "route": "mcp.call_readonly", "tool_name": "srv.read"}
        step, result = classify_step_from_pending_action(
            step_index=3, pending_action=action, observation="mcp read done",
            stopped_for_approval=False
        )
        assert step.kind == "mcp_call"
        assert step.requires_approval is False
        assert result.status == "success"

    def test_mcp_approved_write_classifies_as_apply(self):
        action = {"type": "mcp", "route": "mcp.execute_approved_write", "tool_name": "srv.write"}
        step, result = classify_step_from_pending_action(
            step_index=4, pending_action=action, observation="wrote",
            stopped_for_approval=False
        )
        assert step.kind == "apply"
        assert step.requires_approval is True
        assert result.status == "approved"

    def test_subagent_classifies_as_subagent_dispatch(self):
        action = {"type": "subagent", "route": "subagent.dispatch", "task_id": "t-abc"}
        step, result = classify_step_from_pending_action(
            step_index=5, pending_action=action, observation="subagent done",
            stopped_for_approval=False
        )
        assert step.kind == "subagent_dispatch"
        assert step.requires_approval is False
        assert result.status == "success"

    def test_model_output_invalid_classifies_as_ask(self):
        action = None
        step, result = classify_step_from_pending_action(
            step_index=6, pending_action=action, observation="contract failed",
            stopped_for_approval=False, failure_category="model_output_invalid"
        )
        assert step.kind == "ask"
        assert result.status == "failed"
        assert result.failure_category == "model_output_invalid"

    def test_no_action_defaults_to_ask(self):
        step, result = classify_step_from_pending_action(
            step_index=0, pending_action=None, observation="idle",
            stopped_for_approval=False
        )
        assert step.kind == "ask"

    def test_patch_id_propagated(self):
        action = {"type": "patch", "route": "patch.propose", "patch_id": "p-123"}
        _, result = classify_step_from_pending_action(
            step_index=1, pending_action=action, observation="patch",
            stopped_for_approval=True
        )
        assert result.pending_patch_id == "p-123"

    def test_observation_truncated_in_step_description(self):
        long_obs = "x" * 500
        step, result = classify_step_from_pending_action(
            step_index=0, pending_action=None, observation=long_obs,
            stopped_for_approval=False
        )
        assert len(step.description) <= 200
        assert len(result.summary) <= 500


# ---------------------------------------------------------------------------
# TypedAgentStep model validation
# ---------------------------------------------------------------------------


class TestTypedAgentStep:
    def test_payload_version_is_1(self):
        step = TypedAgentStep.from_route(index=0, kind="ask")
        assert step.payload_version == 1

    def test_created_at_set(self):
        step = TypedAgentStep.from_route(index=0, kind="ask")
        assert step.created_at  # non-empty string

    def test_stop_requires_approval_false(self):
        step = TypedAgentStep.from_route(index=0, kind="stop")
        assert step.requires_approval is False


# ---------------------------------------------------------------------------
# TypedAgentStepResult model validation
# ---------------------------------------------------------------------------


class TestTypedAgentStepResult:
    def test_payload_version_is_1(self):
        result = TypedAgentStepResult(step_index=0, kind="ask", status="success")
        assert result.payload_version == 1

    def test_failure_category_none_by_default(self):
        result = TypedAgentStepResult(step_index=0, kind="ask", status="success")
        assert result.failure_category is None


# ---------------------------------------------------------------------------
# AgentLoop typed projection does not alter existing return contracts
# ---------------------------------------------------------------------------


class TestAgentLoopTypedProjectionContract:
    def test_step_returns_agent_step_result(self, tmp_path, monkeypatch):
        """step() must still return AgentStepResult regardless of typed projection."""
        from safecode.llm.mock import MockLLMClient
        loop = AgentLoop(project_root=tmp_path, llm_client=MockLLMClient())
        result = loop.step("test goal")
        assert isinstance(result, AgentStepResult)
        assert hasattr(result, "state")
        assert hasattr(result, "observation")
        assert hasattr(result, "stopped_for_approval")

    def test_run_returns_agent_run_result(self, tmp_path):
        """run() must still return AgentRunResult."""
        from safecode.llm.mock import MockLLMClient
        loop = AgentLoop(project_root=tmp_path, llm_client=MockLLMClient())
        result = loop.run("test goal", max_steps=2)
        assert isinstance(result, AgentRunResult)
        assert hasattr(result, "state")
        assert hasattr(result, "steps")
        assert hasattr(result, "stopped_reason")

    def test_last_typed_result_available_after_step(self, tmp_path):
        """last_typed_result property returns TypedAgentStepResult after step."""
        from safecode.llm.mock import MockLLMClient
        loop = AgentLoop(project_root=tmp_path, llm_client=MockLLMClient())
        assert loop.last_typed_result is None
        loop.step("test goal")
        assert isinstance(loop.last_typed_result, TypedAgentStepResult)

    def test_last_typed_result_updates_each_step(self, tmp_path):
        """last_typed_result is updated on successive steps."""
        from safecode.llm.mock import MockLLMClient
        loop = AgentLoop(project_root=tmp_path, llm_client=MockLLMClient())
        loop.step("goal one")
        first = loop.last_typed_result
        loop.step(None)
        second = loop.last_typed_result
        # Both are TypedAgentStepResult; step_index may differ
        assert isinstance(first, TypedAgentStepResult)
        assert isinstance(second, TypedAgentStepResult)


# ---------------------------------------------------------------------------
# model_output_invalid after bounded retry
# ---------------------------------------------------------------------------


class TestModelOutputInvalidAfterRetry:
    def test_model_output_invalid_after_retry_does_not_auto_retry(self, tmp_path):
        """When both initial and retry choose_tool calls return RecoverableContractFailure,
        the loop stops with failure_category=model_output_invalid and does not retry again."""
        failure = _contract_failure()
        client = _mock_client_with_response(failure)

        loop = AgentLoop(project_root=tmp_path, llm_client=client)
        result = loop.step("test")

        assert isinstance(result, AgentStepResult)
        assert result.stopped_for_approval is False
        # choose_tool is called twice (initial + one bounded retry), then stops
        assert client.choose_tool.call_count == 2

        typed = loop.last_typed_result
        assert typed is not None
        assert typed.failure_category == "model_output_invalid"
        assert typed.status == "failed"

    def test_model_output_invalid_typed_kind_is_ask(self, tmp_path):
        """model_output_invalid steps are classified as 'ask' kind."""
        failure = _contract_failure()
        client = _mock_client_with_response(failure)
        loop = AgentLoop(project_root=tmp_path, llm_client=client)
        loop.step("test")
        typed = loop.last_typed_result
        assert typed is not None
        assert typed.kind == "ask"


# ---------------------------------------------------------------------------
# Stop-for-user path
# ---------------------------------------------------------------------------


class TestStopForUserTypedStep:
    def test_stop_for_user_classifies_stop_kind(self, tmp_path):
        client = _mock_client_with_response(_stop_response())
        loop = AgentLoop(project_root=tmp_path, llm_client=client)
        result = loop.step("test")
        assert result.stopped_for_approval is True
        typed = loop.last_typed_result
        assert typed is not None
        assert typed.kind == "stop"
        assert typed.status == "waiting_for_user"
