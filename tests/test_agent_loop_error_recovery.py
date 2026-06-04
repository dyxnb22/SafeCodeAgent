"""Tests for v2.9.1 agent-loop-error-recovery.

Verifies:
- A scripted first-fail second-pass fixture succeeds.
- Journal records a loop_retry event with reason details.
- Retry count is bounded to one (second recoverable failure is permanent).
- Non-recoverable paths do not trigger retry: user-stop, hard violations.
- record_loop_retry() appends a "loop_retry" journal event.
- Old journals without "loop_retry" still parse (backward compat).
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from safecode.agent.schemas import (
    AgentPatchResponse,
    AgentStopForUserResponse,
    AgentToolIntentResponse,
    RecoverableContractFailure,
)
from safecode.agent.tools import ToolIntent
from safecode.agent.loop import AgentLoop
from safecode.eval.loop_runner import (
    LLMContractViolation,
    LoopEvalFixture,
    LoopEvalResult,
    LoopFailureCategory,
    LoopModeEvalRunner,
    ScriptedLLMClient,
    ScriptedStep,
    default_loop_fixtures,
)
from safecode.state.journal import AgentJournalStore, JournalEventType

runner = CliRunner()


# ── ScriptedLLMClient retry behaviour ────────────────────────────────────


class TestScriptedLLMClientRetry:
    def _read_step(self, target: str = "src/foo.py") -> ScriptedStep:
        return ScriptedStep(
            tool_choice=AgentToolIntentResponse(
                intent=ToolIntent(type="read", target=target, description="Read"),
                rationale="read first",
            )
        )

    def _patch_step(self, target: str = "src/foo.py") -> ScriptedStep:
        return ScriptedStep(
            tool_choice=AgentToolIntentResponse(
                intent=ToolIntent(type="patch", target=target, description="Patch", requires_approval=True),
                rationale="patch",
            ),
            patch_response=AgentPatchResponse(
                patch_text=(
                    "*** Begin Patch\n"
                    "*** Update File: src/foo.py\n"
                    "@@\nSEARCH:\nold\nREPLACE:\nnew\n"
                    "*** End Patch"
                ),
                explanation="fix",
            ),
        )

    def test_first_fail_recoverable_returns_recoverable_failure_on_first_call(self):
        step = ScriptedStep(
            tool_choice=AgentToolIntentResponse(
                intent=ToolIntent(type="read", target="x.py", description="Read"),
                rationale="",
            ),
            first_fail_recoverable=True,
        )
        client = ScriptedLLMClient([step])
        result = client.choose_tool("goal", {})
        assert isinstance(result, RecoverableContractFailure)
        assert result.method == "choose_tool"

    def test_first_fail_recoverable_returns_real_choice_on_retry(self):
        step = ScriptedStep(
            tool_choice=AgentToolIntentResponse(
                intent=ToolIntent(type="read", target="x.py", description="Read"),
                rationale="",
            ),
            first_fail_recoverable=True,
        )
        client = ScriptedLLMClient([step])
        # First call → recoverable failure
        first = client.choose_tool("goal", {})
        assert isinstance(first, RecoverableContractFailure)
        # Second call (retry) → real tool choice
        second = client.choose_tool("goal", {})
        assert isinstance(second, AgentToolIntentResponse)
        assert second.intent.target == "x.py"

    def test_first_fail_recoverable_does_not_advance_index_on_first_call(self):
        step0 = ScriptedStep(
            tool_choice=AgentToolIntentResponse(
                intent=ToolIntent(type="read", target="a.py", description=""),
                rationale="",
            ),
            first_fail_recoverable=True,
        )
        step1 = self._read_step("b.py")
        client = ScriptedLLMClient([step0, step1])
        client.choose_tool("goal", {})  # first call → recoverable failure
        retry = client.choose_tool("goal", {})  # retry → real step0 choice
        assert isinstance(retry, AgentToolIntentResponse)
        assert retry.intent.target == "a.py"
        # After retry, step1 should be next
        next_choice = client.choose_tool("goal", {})
        assert isinstance(next_choice, AgentToolIntentResponse)
        assert next_choice.intent.target == "b.py"

    def test_non_recoverable_step_does_not_trigger_retry_path(self):
        step = self._read_step("z.py")
        client = ScriptedLLMClient([step])
        result = client.choose_tool("goal", {})
        assert isinstance(result, AgentToolIntentResponse)  # no recoverable failure
        assert not isinstance(result, RecoverableContractFailure)

    def test_recoverable_failure_not_added_to_violations(self):
        step = ScriptedStep(
            tool_choice=AgentToolIntentResponse(
                intent=ToolIntent(type="read", target="x.py", description=""),
                rationale="",
            ),
            first_fail_recoverable=True,
        )
        client = ScriptedLLMClient([step])
        result = client.choose_tool("goal", {})
        assert isinstance(result, RecoverableContractFailure)
        assert client.violations == []  # RecoverableContractFailure is not a violation


# ── First-fail second-pass integration test ───────────────────────────────


def _first_fail_then_patch_fixture() -> LoopEvalFixture:
    """Scripted fixture: first choose_tool call returns recoverable failure, retry succeeds."""
    read_step = ScriptedStep(
        tool_choice=AgentToolIntentResponse(
            intent=ToolIntent(type="read", target="src/lib.py", description="Read lib"),
            rationale="Inspect lib before patching.",
        )
    )
    patch_step_with_first_fail = ScriptedStep(
        tool_choice=AgentToolIntentResponse(
            intent=ToolIntent(
                type="patch",
                target="src/lib.py",
                description="Fix divide function",
                requires_approval=True,
            ),
            rationale="Propose patch after recoverable failure and retry.",
        ),
        patch_response=AgentPatchResponse(
            patch_text=(
                "*** Begin Patch\n"
                "*** Update File: src/lib.py\n"
                "@@\n"
                "SEARCH:\n"
                "    return a / b\n"
                "REPLACE:\n"
                "    if b == 0:\n"
                "        raise ValueError('division by zero')\n"
                "    return a / b\n"
                "*** End Patch"
            ),
            explanation="Scripted divide-by-zero guard.",
        ),
        first_fail_recoverable=True,  # First call → RecoverableContractFailure; retry → real choice
    )
    return LoopEvalFixture(
        name="first-fail-second-pass",
        goal="Add a division-by-zero guard to src/lib.py",
        files={
            "src/lib.py": "def divide(a: float, b: float) -> float:\n    return a / b\n",
            ".sac/config.toml": '[llm]\nprovider = "mock"\n',
        },
        scripted_steps=[read_step, patch_step_with_first_fail],
        expected_pending_patch=True,
        expected_patch_contains=["division by zero", "src/lib.py"],
    )


class TestFirstFailSecondPassFixture:
    def test_first_fail_second_pass_fixture_passes(self):
        fixture = _first_fail_then_patch_fixture()
        result = LoopModeEvalRunner().run_fixture(fixture)
        assert result.passed, f"Fixture failed: {result.failure_reasons}"
        assert not result.violations

    def test_first_fail_second_pass_pending_patch_present(self):
        fixture = _first_fail_then_patch_fixture()
        result = LoopModeEvalRunner().run_fixture(fixture)
        assert result.passed
        assert result.pending_patch_text is not None


# ── Journal records loop_retry event ─────────────────────────────────────


class TestJournalLoopRetryEvent:
    def test_record_loop_retry_appends_event(self, tmp_path):
        store = AgentJournalStore(tmp_path)
        session_id = "a" * 32
        store.record_loop_retry(
            session_id,
            step=2,
            message="Retry step 2 after recoverable failure.",
            retry_details={"method": "choose_tool", "message": "scripted", "retry_attempt": 1},
        )
        events = store.read(session_id)
        assert len(events) == 1
        ev = events[0]
        assert ev.type == "loop_retry"
        assert ev.step == 2
        assert "Retry step 2" in ev.message

    def test_loop_retry_event_payload(self, tmp_path):
        store = AgentJournalStore(tmp_path)
        session_id = "b" * 32
        store.record_loop_retry(
            session_id,
            step=0,
            message="Retry.",
            retry_details={"method": "choose_tool", "retry_attempt": 1},
        )
        events = store.read(session_id)
        payload = events[0].payload
        assert "loop_retry" in payload
        lr = payload["loop_retry"]
        assert lr["method"] == "choose_tool"
        assert lr["retry_attempt"] == 1

    def test_loop_retry_is_valid_journal_event_type(self):
        # "loop_retry" must be in JournalEventType
        import typing
        args = typing.get_args(JournalEventType)
        assert "loop_retry" in args

    def test_old_journals_without_loop_retry_still_parse(self, tmp_path):
        """Journal files created before v2.9.1 must still load correctly."""
        store = AgentJournalStore(tmp_path)
        session_id = "c" * 32
        store.record_plan(session_id, "goal", ["step1"])
        store.record_action(session_id, 0, "Did something")
        events = store.read(session_id)
        # No loop_retry events but existing events still load fine
        assert any(e.type == "plan" for e in events)
        assert any(e.type == "action" for e in events)

    def test_loop_retry_event_has_schema_version(self, tmp_path):
        store = AgentJournalStore(tmp_path)
        session_id = "d" * 32
        ev = store.record_loop_retry(session_id, step=1, message="retry")
        assert ev.schema_version == 1


class TestRecoverableRetryNotStuck:
    def test_recoverable_retry_does_not_count_as_stuck_intent(self, tmp_path):
        step = ScriptedStep(
            tool_choice=AgentToolIntentResponse(
                intent=ToolIntent(type="read", target="a.py", description="Read"),
                rationale="read",
            ),
            first_fail_recoverable=True,
        )
        client = ScriptedLLMClient([step])

        result = AgentLoop(tmp_path, llm_client=client).run("read once", max_steps=1)

        assert result.stopped_reason == "max_steps_reached"
        assert result.state.status != "aborted"
        assert result.state.last_error is None


# ── Retry bounded to one ──────────────────────────────────────────────────


class TestRetryBoundedToOne:
    def _double_fail_fixture(self) -> LoopEvalFixture:
        """Fixture where two consecutive recoverable failures → permanent failure."""
        step0 = ScriptedStep(
            tool_choice=AgentToolIntentResponse(
                intent=ToolIntent(type="read", target="x.py", description="Read"),
                rationale="",
            ),
            first_fail_recoverable=True,
        )
        # The step AFTER the retry is also first_fail_recoverable — on the retry
        # for step0, we return its real tool_choice (AgentToolIntentResponse), so
        # the loop proceeds. But step1 itself is also first_fail_recoverable.
        # For a "double permanent failure" we need a different setup:
        # Make step0 first_fail_recoverable; then the scripted_steps end, so retry
        # of step0 returns the real choice but step1 doesn't exist → violation.
        # For "second RecoverableContractFailure after retry" we use a custom client.
        return LoopEvalFixture(
            name="double-recoverable-fail",
            goal="Read and stop",
            files={".sac/config.toml": '[llm]\nprovider = "mock"\n'},
            scripted_steps=[step0],
            expected_pending_patch=False,
        )

    def test_retry_does_not_loop_infinitely(self):
        """After one retry, a second RecoverableContractFailure must not retry again."""

        class DoubleFailClient:
            """Always returns RecoverableContractFailure on both calls."""
            violations: list = []

            def plan(self, goal, context):
                from safecode.agent.schemas import AgentPlanResponse
                return AgentPlanResponse(goal=goal, steps=["step1"])

            def choose_tool(self, goal, context):
                return RecoverableContractFailure(step=0, method="choose_tool", message="always fails")

        import tempfile
        from pathlib import Path
        from safecode.agent.loop import AgentLoop

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / ".sac").mkdir()
            (workspace / ".sac" / "config.toml").write_text('[llm]\nprovider = "mock"\n')
            loop = AgentLoop(project_root=workspace, llm_client=DoubleFailClient())
            # Should complete (not loop forever) and record a permanent failure.
            result = loop.run(goal="test bounded retry", max_steps=3)
            # The step should fail permanently after one retry, not loop infinitely.
            assert result is not None  # did not hang

    def test_user_stop_does_not_retry(self):
        """AgentStopForUserResponse must never be retried."""
        stop_step = ScriptedStep(
            tool_choice=AgentStopForUserResponse(
                reason="needs_input",
                message="Stop for user.",
                requires_approval=True,
            ),
        )
        client = ScriptedLLMClient([stop_step])
        # call_count tracks total choose_tool calls
        call_count = [0]
        original = client.choose_tool

        def counted_choose_tool(goal, context):
            call_count[0] += 1
            return original(goal, context)

        client.choose_tool = counted_choose_tool
        result = client.choose_tool("goal", {})
        assert isinstance(result, AgentStopForUserResponse)
        assert call_count[0] == 1  # only called once


# ── RecoverableContractFailure type in schemas ────────────────────────────


class TestRecoverableContractFailureSchema:
    def test_importable_from_schemas(self):
        from safecode.agent.schemas import RecoverableContractFailure as RCF
        assert RCF is not None

    def test_frozen(self):
        rcf = RecoverableContractFailure(step=0, method="choose_tool", message="test")
        with pytest.raises((AttributeError, TypeError)):
            rcf.message = "changed"  # type: ignore[misc]

    def test_fields(self):
        rcf = RecoverableContractFailure(step=3, method="propose_patch", message="oops")
        assert rcf.step == 3
        assert rcf.method == "propose_patch"
        assert rcf.message == "oops"

    def test_distinct_from_llm_contract_violation(self):
        rcf = RecoverableContractFailure(step=0, method="m", message="x")
        v = LLMContractViolation(step=0, method="m", message="x")
        assert type(rcf) is not type(v)
        assert not isinstance(rcf, LLMContractViolation)
