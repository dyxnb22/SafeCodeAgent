"""Tests for v2.2.4: Subagent Orchestration."""

from __future__ import annotations

import pytest

from safecode.agent.loop import AgentLoop
from safecode.agent.tools import ToolIntentRouter
from safecode.state.journal import AgentJournalStore
from safecode.subagents.executor import SubagentDispatchExecutor, SubagentRequest, SubagentResult
from safecode.subagents.runner import ReadonlySubagentRunner
from safecode.tools.adapter import AdapterError, ToolCallAdapter
from safecode.tools.registry import PermissionCategory, ToolRegistry


# ── Registry: subagent.dispatch spec ─────────────────────────────────────────


class TestSubagentDispatchRegistry:
    def test_dispatch_spec_exists(self):
        spec = ToolRegistry().get("subagent.dispatch")
        assert spec.name == "subagent.dispatch"

    def test_dispatch_spec_is_readonly_no_approval(self):
        spec = ToolRegistry().get("subagent.dispatch")
        assert spec.requires_human_approval is False
        assert spec.permission_category == PermissionCategory.SUBAGENT

    def test_dispatch_spec_has_required_args(self):
        spec = ToolRegistry().get("subagent.dispatch")
        arg_names = {a.name for a in spec.args}
        assert "task" in arg_names
        assert "scope" in arg_names
        assert "max_steps" in arg_names

    def test_dispatch_spec_task_is_required(self):
        spec = ToolRegistry().get("subagent.dispatch")
        arg = next(a for a in spec.args if a.name == "task")
        assert arg.required is True
        assert arg.type == "str"

    def test_dispatch_spec_scope_is_required(self):
        spec = ToolRegistry().get("subagent.dispatch")
        arg = next(a for a in spec.args if a.name == "scope")
        assert arg.required is True
        assert arg.type == "str"

    def test_dispatch_spec_max_steps_is_int(self):
        spec = ToolRegistry().get("subagent.dispatch")
        arg = next(a for a in spec.args if a.name == "max_steps")
        assert arg.required is True
        assert arg.type == "int"

    def test_dispatch_spec_has_audit_event(self):
        spec = ToolRegistry().get("subagent.dispatch")
        assert spec.audit_event is not None
        assert spec.audit_event.event_type == "subagent_dispatched"

    def test_dispatch_adapter_validates_correct_args(self):
        result = ToolCallAdapter().validate(
            "subagent.dispatch", {"task": "investigate", "scope": "src/", "max_steps": 3}
        )
        assert result.tool_name == "subagent.dispatch"
        assert result.requires_approval is False

    def test_dispatch_adapter_rejects_missing_task(self):
        with pytest.raises(AdapterError, match="Missing required argument 'task'"):
            ToolCallAdapter().validate(
                "subagent.dispatch", {"scope": "src/", "max_steps": 3}
            )

    def test_dispatch_adapter_rejects_missing_scope(self):
        with pytest.raises(AdapterError, match="Missing required argument 'scope'"):
            ToolCallAdapter().validate(
                "subagent.dispatch", {"task": "investigate", "max_steps": 3}
            )

    def test_dispatch_adapter_rejects_missing_max_steps(self):
        with pytest.raises(AdapterError, match="Missing required argument 'max_steps'"):
            ToolCallAdapter().validate(
                "subagent.dispatch", {"task": "investigate", "scope": "src/"}
            )

    def test_dispatch_adapter_rejects_wrong_max_steps_type(self):
        with pytest.raises(AdapterError, match="max_steps"):
            ToolCallAdapter().validate(
                "subagent.dispatch",
                {"task": "investigate", "scope": "src/", "max_steps": "3"},
            )


# ── Router: subagent intent routing ──────────────────────────────────────────


class TestSubagentRouter:
    def test_subagent_routes_to_dispatch(self):
        routed = ToolIntentRouter().route(
            {"type": "subagent", "task_id": "abc123", "description": "inspect tests"}
        )
        assert routed.route == "subagent.dispatch"

    def test_subagent_is_executable_without_approval(self):
        routed = ToolIntentRouter().route(
            {"type": "subagent", "task_id": "abc123", "description": "inspect tests"}
        )
        assert routed.executable_now is True
        assert routed.intent.requires_approval is False

    def test_subagent_reason_is_safe_to_route(self):
        routed = ToolIntentRouter().route(
            {"type": "subagent", "task_id": "abc123"}
        )
        assert routed.reason == "safe_to_route"

    def test_subagent_intent_task_id_preserved(self):
        routed = ToolIntentRouter().route(
            {"type": "subagent", "task_id": "myid42"}
        )
        assert routed.intent.task_id == "myid42"


# ── SubagentRequest model ─────────────────────────────────────────────────────


class TestSubagentRequest:
    def test_request_is_frozen_dataclass(self):
        req = SubagentRequest(task="check files", scope="src/", max_steps=3)
        assert req.task == "check files"
        assert req.scope == "src/"
        assert req.max_steps == 3

    def test_request_is_immutable(self):
        req = SubagentRequest(task="t", scope="s", max_steps=2)
        with pytest.raises((AttributeError, TypeError)):
            req.task = "other"  # type: ignore[misc]


# ── SubagentDispatchExecutor ──────────────────────────────────────────────────


class TestSubagentDispatchExecutor:
    def test_execute_returns_subagent_result(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("Check test files", "tests/", 2)
        assert isinstance(result, SubagentResult)

    def test_execute_success_returns_task_id(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("Investigate imports", "src/", 3)
        assert result.success is True
        assert result.task_id != ""

    def test_execute_returns_structured_fields(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("Find all models", "src/safecode/", 2)
        assert isinstance(result.summary, str)
        assert isinstance(result.observations, list)
        assert isinstance(result.files_inspected, list)
        assert isinstance(result.commands_attempted, list)
        assert isinstance(result.blocked_actions, list)
        assert isinstance(result.errors, list)

    def test_execute_commands_attempted_is_empty(self, tmp_path):
        """Subagents must not attempt shell commands."""
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("Review config", "src/", 1)
        assert result.commands_attempted == []

    def test_execute_blocked_actions_empty_on_success(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("Check project", ".", 1)
        assert result.blocked_actions == []

    def test_execute_fails_closed_on_max_steps_too_large(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("task", "scope", 99)
        assert result.success is False
        assert result.blocked is True
        assert result.errors != []

    def test_execute_fails_closed_on_max_steps_zero(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("task", "scope", 0)
        assert result.success is False
        assert result.blocked is True

    def test_execute_fails_closed_on_empty_task(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("   ", "src/", 2)
        assert result.success is False
        assert result.blocked is True

    def test_execute_never_raises(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        # Even with bad args, should not raise
        result = executor.execute("", "", -1)
        assert isinstance(result, SubagentResult)

    def test_write_attempt_is_blocked(self, tmp_path):
        """Executor must not modify files outside .sac/subagents/."""
        target = tmp_path / "should_not_be_written.txt"
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("write to project files", str(target), 1)
        assert not target.exists(), "Subagent must not write project files"
        # Execution should complete (result file stays in .sac/subagents/)
        assert isinstance(result, SubagentResult)

    def test_result_is_written_inside_sac_subagents(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("Check readme", ".", 1)
        assert result.success is True
        sac_subagents = tmp_path / ".sac" / "subagents"
        assert sac_subagents.exists()
        task_dir = sac_subagents / result.task_id
        assert task_dir.exists()
        result_file = task_dir / "result.md"
        assert result_file.exists()

    def test_each_dispatch_creates_unique_task(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        r1 = executor.execute("First task", "src/", 1)
        r2 = executor.execute("Second task", "src/", 1)
        assert r1.task_id != r2.task_id

    def test_missing_scope_returns_blocked_not_empty_string(self, tmp_path):
        """None scope must not silently become '' and pass adapter validation."""
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("task", None, 3)
        assert result.blocked is True
        assert result.success is False
        assert result.errors != []

    def test_missing_max_steps_returns_blocked_not_default_3(self, tmp_path):
        """None max_steps must not silently default to 3 and execute."""
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("task", "src/", None)
        assert result.blocked is True
        assert result.success is False
        assert result.errors != []

    def test_non_int_max_steps_returns_blocked_not_raises(self, tmp_path):
        """String max_steps must block, not raise ValueError from int()."""
        executor = SubagentDispatchExecutor(tmp_path)
        result = executor.execute("task", "src/", "three")
        assert result.blocked is True
        assert result.success is False


# ── AgentLoop: arg validation tightening ─────────────────────────────────────


class TestAgentLoopDispatchArgValidation:
    """Verify that the loop passes raw input_json values without masking bad args."""

    def _make_loop_with_intent(self, tmp_path, monkeypatch, input_json):
        """Set up AgentLoop patched to emit a subagent intent with the given input_json."""
        from safecode.agent.schemas import AgentToolIntentResponse, AgentPlanResponse
        from safecode.agent.tools import ToolIntent

        def fake_plan(self_llm, goal, context):
            return AgentPlanResponse(type="plan", goal=goal, steps=["Subagent step"])

        def fake_choose_tool(self_llm, goal, context):
            return AgentToolIntentResponse(
                type="tool_intent",
                intent=ToolIntent(
                    type="subagent",
                    task_id="validation_test",
                    description="fallback description",
                    input_json=input_json,
                ),
            )

        monkeypatch.setattr("safecode.llm.mock.MockLLMClient.plan", fake_plan)
        monkeypatch.setattr("safecode.llm.mock.MockLLMClient.choose_tool", fake_choose_tool)
        return AgentLoop(tmp_path)

    def test_missing_max_steps_does_not_execute_as_default_3(self, tmp_path, monkeypatch):
        """input_json with no max_steps must produce a blocked result, not run with max_steps=3."""
        loop = self._make_loop_with_intent(
            tmp_path, monkeypatch, {"task": "check files", "scope": "src/"}
        )
        result = loop.step(goal="check files")
        assert result.stopped_for_approval is False
        # Must be a blocked observation, not a successful subagent run.
        assert "Subagent" in result.observation
        state = loop.store.load()
        assert state.pending_action["subagent_blocked"] == "true"

    def test_missing_scope_does_not_execute_as_empty_string(self, tmp_path, monkeypatch):
        """input_json with no scope must produce a blocked result, not run with scope=''."""
        loop = self._make_loop_with_intent(
            tmp_path, monkeypatch, {"task": "check files", "max_steps": 2}
        )
        result = loop.step(goal="check files")
        assert result.stopped_for_approval is False
        state = loop.store.load()
        assert state.pending_action["subagent_blocked"] == "true"

    def test_non_int_max_steps_does_not_raise_from_step(self, tmp_path, monkeypatch):
        """String max_steps in input_json must not propagate a ValueError through AgentLoop.step()."""
        loop = self._make_loop_with_intent(
            tmp_path, monkeypatch, {"task": "check", "scope": "src/", "max_steps": "three"}
        )
        result = loop.step(goal="check")  # must not raise
        assert result.stopped_for_approval is False
        state = loop.store.load()
        assert state.pending_action["subagent_blocked"] == "true"

    def test_blocked_dispatch_records_journal_event_with_failure_fields(self, tmp_path, monkeypatch):
        """A blocked subagent dispatch must still write a subagent_dispatch journal event."""
        loop = self._make_loop_with_intent(
            tmp_path, monkeypatch, {"task": "check", "scope": "src/"}  # missing max_steps
        )
        loop.step(goal="check")
        session_id = loop.store.load().session_id
        events = AgentJournalStore(tmp_path).read(session_id)
        dispatch_events = [e for e in events if e.type == "subagent_dispatch"]
        assert len(dispatch_events) == 1
        payload = dispatch_events[0].payload["subagent_dispatch"]
        assert payload["success"] is False
        assert payload["blocked"] is True

    def test_input_json_task_preferred_over_description(self, tmp_path, monkeypatch):
        """task from input_json takes precedence over intent.description."""
        loop = self._make_loop_with_intent(
            tmp_path, monkeypatch,
            {"task": "from_input_json", "scope": "src/", "max_steps": 1},
        )
        loop.step(goal="ignored goal")
        session_id = loop.store.load().session_id
        events = AgentJournalStore(tmp_path).read(session_id)
        dispatch_events = [e for e in events if e.type == "subagent_dispatch"]
        assert len(dispatch_events) == 1
        assert dispatch_events[0].payload["subagent_dispatch"]["task"] == "from_input_json"


# ── Journal: subagent_dispatch event type ────────────────────────────────────


class TestSubagentJournal:
    def test_record_subagent_dispatch_creates_event(self, tmp_path):
        store = AgentJournalStore(tmp_path)
        session_id = "testses001"
        event = store.record_subagent_dispatch(
            session_id,
            step=1,
            message="Subagent ran",
            dispatch_summary={
                "task_id": "abc",
                "task": "check files",
                "scope": "src/",
                "max_steps": 3,
                "summary": "Found 10 files",
                "success": True,
                "blocked": False,
            },
        )
        assert event.type == "subagent_dispatch"
        assert event.session_id == session_id
        assert event.step == 1

    def test_subagent_dispatch_event_has_payload(self, tmp_path):
        store = AgentJournalStore(tmp_path)
        event = store.record_subagent_dispatch(
            "testses002",
            step=2,
            message="done",
            dispatch_summary={"task_id": "t1", "success": True},
        )
        assert "subagent_dispatch" in event.payload
        assert event.payload["subagent_dispatch"]["task_id"] == "t1"

    def test_subagent_dispatch_event_is_persisted(self, tmp_path):
        store = AgentJournalStore(tmp_path)
        store.record_subagent_dispatch(
            "testses003", step=1, message="persisted", dispatch_summary={"task_id": "x"}
        )
        events = store.read("testses003")
        assert any(e.type == "subagent_dispatch" for e in events)

    def test_journal_event_type_literal_includes_subagent_dispatch(self):
        from safecode.state.journal import JournalEventType
        import typing
        args = typing.get_args(JournalEventType)
        assert "subagent_dispatch" in args


# ── AgentLoop: subagent dispatch integration ─────────────────────────────────


class TestAgentLoopSubagentDispatch:
    def test_loop_dispatches_subagent_and_journals_result(self, tmp_path, monkeypatch):
        """AgentLoop routes subagent intent to dispatch executor and journals result."""
        from safecode.agent.schemas import AgentToolIntentResponse
        from safecode.agent.tools import ToolIntent
        from safecode.llm.mock import MockLLMClient
        from safecode.agent.schemas import AgentPlanResponse

        # Patch LLM to return a subagent intent
        def fake_plan(self_llm, goal, context):
            return AgentPlanResponse(
                type="plan", goal=goal, steps=["Dispatch subagent to inspect src/"]
            )

        def fake_choose_tool(self_llm, goal, context):
            return AgentToolIntentResponse(
                type="tool_intent",
                intent=ToolIntent(
                    type="subagent",
                    task_id="loop_test_task",
                    description="Check all source files",
                    input_json={"scope": "src/", "max_steps": 2},
                ),
            )

        monkeypatch.setattr(
            "safecode.llm.mock.MockLLMClient.plan", fake_plan
        )
        monkeypatch.setattr(
            "safecode.llm.mock.MockLLMClient.choose_tool", fake_choose_tool
        )

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="Inspect the source tree")

        assert "Subagent" in result.observation
        assert result.stopped_for_approval is False

        journal = AgentJournalStore(tmp_path)
        session_id = loop.store.load().session_id
        events = journal.read(session_id)
        dispatch_events = [e for e in events if e.type == "subagent_dispatch"]
        assert len(dispatch_events) == 1
        payload = dispatch_events[0].payload["subagent_dispatch"]
        assert payload["task"] == "Check all source files"
        assert payload["scope"] == "src/"

    def test_loop_subagent_result_merged_as_observation(self, tmp_path, monkeypatch):
        """Subagent result summary appears in the step observation."""
        from safecode.agent.schemas import AgentToolIntentResponse, AgentPlanResponse
        from safecode.agent.tools import ToolIntent

        def fake_plan(self_llm, goal, context):
            return AgentPlanResponse(type="plan", goal=goal, steps=["Subagent step"])

        def fake_choose_tool(self_llm, goal, context):
            return AgentToolIntentResponse(
                type="tool_intent",
                intent=ToolIntent(
                    type="subagent",
                    task_id="obs_test",
                    description="Summarize config files",
                    input_json={"scope": ".", "max_steps": 1},
                ),
            )

        monkeypatch.setattr("safecode.llm.mock.MockLLMClient.plan", fake_plan)
        monkeypatch.setattr("safecode.llm.mock.MockLLMClient.choose_tool", fake_choose_tool)

        loop = AgentLoop(tmp_path)
        result = loop.step(goal="Summarize config")

        # Observation should contain task_id and summary text
        assert "Subagent" in result.observation
        state = loop.store.load()
        assert state.pending_action is not None
        assert state.pending_action.get("type") == "subagent"


# ── Existing MCP behavior unchanged ──────────────────────────────────────────


class TestExistingMCPUnchanged:
    def test_mcp_readonly_route_unchanged(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "notion.search"})
        assert routed.route == "mcp.call_readonly"
        assert routed.executable_now is True

    def test_mcp_write_route_unchanged(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "notion.create"})
        assert routed.route == "mcp.propose"
        assert routed.executable_now is False

    def test_mcp_unknown_requires_approval(self):
        routed = ToolIntentRouter().route({"type": "mcp", "tool_name": "server.xyzzy"})
        assert routed.route == "mcp.propose"
        assert routed.intent.requires_approval is True

    def test_mcp_readonly_spec_still_exists(self):
        spec = ToolRegistry().get("mcp.call_readonly")
        assert spec.requires_human_approval is False

    def test_mcp_propose_write_spec_still_exists(self):
        spec = ToolRegistry().get("mcp.propose_write")
        assert spec.requires_human_approval is True


# ── Merge policy: SubagentFinding / MergedSubagentContext ────────────────────


from safecode.subagents.merge_policy import (  # noqa: E402
    MergedSubagentContext,
    SubagentFinding,
    merge_subagent_findings,
)


class TestMergePolicyDataclasses:
    def test_subagent_finding_is_frozen(self):
        f = SubagentFinding(task_id="t1", summary="s", success=True)
        with pytest.raises((AttributeError, TypeError)):
            f.task_id = "other"  # type: ignore[misc]

    def test_merged_context_is_frozen(self):
        m = MergedSubagentContext(summary="x")
        with pytest.raises((AttributeError, TypeError)):
            m.summary = "y"  # type: ignore[misc]

    def test_subagent_finding_defaults(self):
        f = SubagentFinding(task_id="t", summary="s")
        assert f.observations == []
        assert f.files_inspected == []
        assert f.errors == []
        assert f.blocked is False
        assert f.success is False

    def test_merged_context_defaults(self):
        m = MergedSubagentContext(summary="")
        assert m.observations == []
        assert m.files_inspected == []
        assert m.source_task_ids == []
        assert m.blocked_task_ids == []
        assert m.errors == []


class TestMergeSubagentFindingsEmpty:
    def test_empty_list_returns_merged_context(self):
        result = merge_subagent_findings([])
        assert isinstance(result, MergedSubagentContext)

    def test_empty_list_summary_is_empty_string(self):
        result = merge_subagent_findings([])
        assert result.summary == ""

    def test_empty_list_all_lists_empty(self):
        result = merge_subagent_findings([])
        assert result.observations == []
        assert result.files_inspected == []
        assert result.source_task_ids == []
        assert result.blocked_task_ids == []
        assert result.errors == []


class TestMergeSubagentFindingsOrdering:
    def test_observations_preserve_input_order(self):
        findings = [
            SubagentFinding(task_id="t1", summary="", observations=["obs_c", "obs_a"], success=True),
            SubagentFinding(task_id="t2", summary="", observations=["obs_b"], success=True),
        ]
        result = merge_subagent_findings(findings)
        assert result.observations == ["obs_c", "obs_a", "obs_b"]

    def test_files_preserve_input_order(self):
        findings = [
            SubagentFinding(task_id="t1", summary="", files_inspected=["z.py", "a.py"], success=True),
            SubagentFinding(task_id="t2", summary="", files_inspected=["m.py"], success=True),
        ]
        result = merge_subagent_findings(findings)
        assert result.files_inspected == ["z.py", "a.py", "m.py"]

    def test_source_task_ids_preserve_input_order(self):
        findings = [
            SubagentFinding(task_id="first", summary="", success=True),
            SubagentFinding(task_id="second", summary="", success=True),
            SubagentFinding(task_id="third", summary="", success=True),
        ]
        result = merge_subagent_findings(findings)
        assert result.source_task_ids == ["first", "second", "third"]


class TestMergeSubagentFindingsDedupe:
    def test_duplicate_observations_deduplicated_first_wins(self):
        findings = [
            SubagentFinding(task_id="t1", summary="", observations=["obs_a", "obs_b"], success=True),
            SubagentFinding(task_id="t2", summary="", observations=["obs_b", "obs_c"], success=True),
        ]
        result = merge_subagent_findings(findings)
        assert result.observations == ["obs_a", "obs_b", "obs_c"]

    def test_duplicate_files_deduplicated_first_wins(self):
        findings = [
            SubagentFinding(task_id="t1", summary="", files_inspected=["a.py", "b.py"], success=True),
            SubagentFinding(task_id="t2", summary="", files_inspected=["b.py", "c.py"], success=True),
        ]
        result = merge_subagent_findings(findings)
        assert result.files_inspected == ["a.py", "b.py", "c.py"]

    def test_same_observation_three_times_appears_once(self):
        findings = [
            SubagentFinding(task_id=f"t{i}", summary="", observations=["dup"], success=True)
            for i in range(3)
        ]
        result = merge_subagent_findings(findings)
        assert result.observations.count("dup") == 1


class TestMergeSubagentFindingsCaps:
    def test_max_observations_cap_enforced(self):
        findings = [
            SubagentFinding(
                task_id="t1",
                summary="",
                observations=[f"obs_{i}" for i in range(30)],
                success=True,
            )
        ]
        result = merge_subagent_findings(findings, max_observations=10)
        assert len(result.observations) == 10

    def test_max_files_cap_enforced(self):
        findings = [
            SubagentFinding(
                task_id="t1",
                summary="",
                files_inspected=[f"file_{i}.py" for i in range(60)],
                success=True,
            )
        ]
        result = merge_subagent_findings(findings, max_files=25)
        assert len(result.files_inspected) == 25

    def test_cap_preserves_first_entries(self):
        observations = [f"obs_{i}" for i in range(10)]
        findings = [
            SubagentFinding(task_id="t1", summary="", observations=observations, success=True)
        ]
        result = merge_subagent_findings(findings, max_observations=5)
        assert result.observations == observations[:5]

    def test_default_caps_are_20_and_50(self):
        findings = [
            SubagentFinding(
                task_id="t1",
                summary="",
                observations=[f"o{i}" for i in range(25)],
                files_inspected=[f"f{i}.py" for i in range(55)],
                success=True,
            )
        ]
        result = merge_subagent_findings(findings)
        assert len(result.observations) == 20
        assert len(result.files_inspected) == 50


class TestMergeSubagentFindingsBlocked:
    def test_blocked_finding_excluded_from_summary(self):
        findings = [
            SubagentFinding(task_id="t1", summary="good summary", success=True),
            SubagentFinding(task_id="t2", summary="blocked summary", blocked=True, success=False),
        ]
        result = merge_subagent_findings(findings)
        assert "blocked summary" not in result.summary
        assert "good summary" in result.summary

    def test_blocked_task_id_collected(self):
        findings = [
            SubagentFinding(task_id="blocked_task", summary="", blocked=True, success=False),
        ]
        result = merge_subagent_findings(findings)
        assert "blocked_task" in result.blocked_task_ids

    def test_blocked_errors_collected(self):
        findings = [
            SubagentFinding(
                task_id="t1", summary="", blocked=True, success=False, errors=["some error"]
            ),
        ]
        result = merge_subagent_findings(findings)
        assert "some error" in result.errors

    def test_blocked_observations_excluded(self):
        findings = [
            SubagentFinding(
                task_id="t1",
                summary="",
                blocked=True,
                success=False,
                observations=["secret obs"],
            ),
        ]
        result = merge_subagent_findings(findings)
        assert "secret obs" not in result.observations

    def test_failed_non_blocked_also_excluded_from_summary(self):
        findings = [
            SubagentFinding(task_id="t1", summary="fail summary", success=False, blocked=False),
        ]
        result = merge_subagent_findings(findings)
        assert "fail summary" not in result.summary
        assert result.blocked_task_ids == ["t1"]

    def test_only_successful_go_to_source_task_ids(self):
        findings = [
            SubagentFinding(task_id="ok", summary="s", success=True),
            SubagentFinding(task_id="fail", summary="", success=False),
        ]
        result = merge_subagent_findings(findings)
        assert "ok" in result.source_task_ids
        assert "fail" not in result.source_task_ids

    def test_mixed_blocked_and_success(self):
        findings = [
            SubagentFinding(task_id="a", summary="A summary", observations=["obs_a"], success=True),
            SubagentFinding(task_id="b", summary="B", blocked=True, errors=["err_b"], success=False),
            SubagentFinding(task_id="c", summary="C summary", observations=["obs_c"], success=True),
        ]
        result = merge_subagent_findings(findings)
        assert result.source_task_ids == ["a", "c"]
        assert result.blocked_task_ids == ["b"]
        assert "obs_a" in result.observations
        assert "obs_c" in result.observations
        assert "err_b" in result.errors


class TestMergeSubagentFindingsEdgeCases:
    def test_never_raises_on_empty_fields(self):
        f = SubagentFinding(task_id="", summary="", observations=[], files_inspected=[], errors=[], success=True)
        result = merge_subagent_findings([f])
        assert isinstance(result, MergedSubagentContext)

    def test_single_successful_finding(self):
        f = SubagentFinding(
            task_id="only",
            summary="the summary",
            observations=["one obs"],
            files_inspected=["one.py"],
            success=True,
        )
        result = merge_subagent_findings([f])
        assert result.summary == "the summary"
        assert result.observations == ["one obs"]
        assert result.files_inspected == ["one.py"]
        assert result.source_task_ids == ["only"]
        assert result.blocked_task_ids == []
        assert result.errors == []

    def test_all_blocked_gives_empty_summary(self):
        findings = [
            SubagentFinding(task_id="x", summary="nope", blocked=True, success=False),
        ]
        result = merge_subagent_findings(findings)
        assert result.summary == ""
        assert result.observations == []
        assert result.files_inspected == []


class TestMergeFromSubagentResult:
    """Integration: convert SubagentResult to SubagentFinding and merge."""

    def test_successful_result_converts_to_finding(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        sub_result = executor.execute("Inspect src", "src/", 1)

        finding = SubagentFinding(
            task_id=sub_result.task_id,
            summary=sub_result.summary,
            observations=list(sub_result.observations),
            files_inspected=list(sub_result.files_inspected),
            errors=list(sub_result.errors),
            blocked=sub_result.blocked,
            success=sub_result.success,
        )
        merged = merge_subagent_findings([finding])
        assert isinstance(merged, MergedSubagentContext)
        if sub_result.success:
            assert sub_result.task_id in merged.source_task_ids
        else:
            assert sub_result.task_id in merged.blocked_task_ids

    def test_two_results_merged_correctly(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        r1 = executor.execute("First task", "src/", 1)
        r2 = executor.execute("Second task", "tests/", 1)

        findings = [
            SubagentFinding(
                task_id=r.task_id,
                summary=r.summary,
                observations=list(r.observations),
                files_inspected=list(r.files_inspected),
                errors=list(r.errors),
                blocked=r.blocked,
                success=r.success,
            )
            for r in [r1, r2]
        ]
        merged = merge_subagent_findings(findings)
        assert isinstance(merged, MergedSubagentContext)
        successful = [f for f in findings if f.success]
        assert len(merged.source_task_ids) == len(successful)

    def test_blocked_result_contributes_errors_and_not_to_source(self, tmp_path):
        executor = SubagentDispatchExecutor(tmp_path)
        blocked = executor.execute("task", "scope", 99)  # max_steps out of range → blocked
        assert blocked.blocked

        finding = SubagentFinding(
            task_id=blocked.task_id,
            summary=blocked.summary,
            observations=list(blocked.observations),
            files_inspected=list(blocked.files_inspected),
            errors=list(blocked.errors),
            blocked=blocked.blocked,
            success=blocked.success,
        )
        merged = merge_subagent_findings([finding])
        # task_id is empty string when blocked before task creation — not added to blocked_task_ids
        assert "" not in merged.source_task_ids
        assert merged.errors != [] or merged.blocked_task_ids == []  # errors propagated
        assert merged.summary == ""  # no successful summary


# ── v2.2.6: Journal adapter — payload conversion ─────────────────────────────


from safecode.subagents.journal_adapter import (  # noqa: E402
    findings_from_journal_events,
    merge_journal_subagent_findings,
)
from safecode.state.journal import AgentJournalEvent  # noqa: E402


class TestJournalAdapterConversion:
    def _make_dispatch_event(self, session_id: str = "sess01", **payload_overrides) -> AgentJournalEvent:
        payload = {
            "task_id": "t1",
            "summary": "Found 5 files",
            "observations": ["obs_a", "obs_b"],
            "files_inspected": ["a.py", "b.py"],
            "errors": [],
            "blocked": False,
            "success": True,
        }
        payload.update(payload_overrides)
        return AgentJournalEvent(
            session_id=session_id,
            type="subagent_dispatch",
            message="done",
            payload={"subagent_dispatch": payload},
        )

    def test_valid_successful_event_converts_to_finding(self):
        event = self._make_dispatch_event()
        findings = findings_from_journal_events([event])
        assert len(findings) == 1
        f = findings[0]
        assert f.task_id == "t1"
        assert f.summary == "Found 5 files"
        assert f.success is True
        assert f.blocked is False

    def test_observations_and_files_preserved(self):
        event = self._make_dispatch_event()
        findings = findings_from_journal_events([event])
        assert findings[0].observations == ["obs_a", "obs_b"]
        assert findings[0].files_inspected == ["a.py", "b.py"]

    def test_blocked_event_converts_to_blocked_finding(self):
        event = self._make_dispatch_event(blocked=True, success=False, errors=["validation failed"])
        findings = findings_from_journal_events([event])
        assert len(findings) == 1
        f = findings[0]
        assert f.blocked is True
        assert f.success is False
        assert "validation failed" in f.errors

    def test_non_dispatch_events_are_skipped(self):
        plan_event = AgentJournalEvent(
            session_id="sess01",
            type="plan",
            message="planned",
            payload={"goal": "x", "steps": []},
        )
        dispatch_event = self._make_dispatch_event()
        findings = findings_from_journal_events([plan_event, dispatch_event])
        assert len(findings) == 1

    def test_empty_event_list_returns_empty(self):
        assert findings_from_journal_events([]) == []

    def test_ordering_preserved_across_events(self):
        e1 = self._make_dispatch_event(session_id="s1", task_id="first", observations=["obs1"])
        e2 = self._make_dispatch_event(session_id="s1", task_id="second", observations=["obs2"])
        findings = findings_from_journal_events([e1, e2])
        assert findings[0].task_id == "first"
        assert findings[1].task_id == "second"


class TestJournalAdapterMalformedPayloads:
    def test_missing_subagent_dispatch_key_returns_no_finding(self):
        event = AgentJournalEvent(
            session_id="sess01",
            type="subagent_dispatch",
            message="bad",
            payload={},  # no "subagent_dispatch" key
        )
        findings = findings_from_journal_events([event])
        assert findings == []

    def test_non_dict_payload_value_skipped(self):
        event = AgentJournalEvent(
            session_id="sess01",
            type="subagent_dispatch",
            message="bad",
            payload={"subagent_dispatch": "not a dict"},
        )
        findings = findings_from_journal_events([event])
        assert findings == []

    def test_null_payload_value_skipped(self):
        event = AgentJournalEvent(
            session_id="sess01",
            type="subagent_dispatch",
            message="null",
            payload={"subagent_dispatch": None},
        )
        findings = findings_from_journal_events([event])
        assert findings == []

    def test_non_list_observations_skipped(self):
        event = AgentJournalEvent(
            session_id="sess01",
            type="subagent_dispatch",
            message="bad obs",
            payload={"subagent_dispatch": {
                "task_id": "t1",
                "summary": "s",
                "observations": "not a list",
                "success": True,
                "blocked": False,
            }},
        )
        findings = findings_from_journal_events([event])
        assert findings == []

    def test_non_list_files_inspected_skipped(self):
        event = AgentJournalEvent(
            session_id="sess01",
            type="subagent_dispatch",
            message="bad files",
            payload={"subagent_dispatch": {
                "task_id": "t1",
                "summary": "s",
                "files_inspected": "not a list",
                "success": True,
                "blocked": False,
            }},
        )
        findings = findings_from_journal_events([event])
        assert findings == []

    def test_non_list_errors_skipped(self):
        event = AgentJournalEvent(
            session_id="sess01",
            type="subagent_dispatch",
            message="bad errors",
            payload={"subagent_dispatch": {
                "task_id": "t1",
                "summary": "s",
                "errors": "not a list",
                "success": False,
                "blocked": True,
            }},
        )
        findings = findings_from_journal_events([event])
        assert findings == []

    def test_malformed_event_does_not_crash_adapter(self):
        events = [
            AgentJournalEvent(
                session_id="sess01",
                type="subagent_dispatch",
                message="m",
                payload={"subagent_dispatch": None},
            ),
            AgentJournalEvent(
                session_id="sess01",
                type="subagent_dispatch",
                message="m2",
                payload={"subagent_dispatch": {"task_id": "ok", "summary": "good", "success": True, "blocked": False}},
            ),
        ]
        findings = findings_from_journal_events(events)
        assert len(findings) == 1
        assert findings[0].task_id == "ok"

    def test_merge_journal_findings_never_raises_on_empty(self):
        result = merge_journal_subagent_findings([])
        assert isinstance(result, MergedSubagentContext)
        assert result.summary == ""

    def test_merge_journal_findings_never_raises_on_malformed(self):
        event = AgentJournalEvent(
            session_id="sess01",
            type="subagent_dispatch",
            message="m",
            payload={"subagent_dispatch": 42},
        )
        result = merge_journal_subagent_findings([event])
        assert isinstance(result, MergedSubagentContext)

    def test_malformed_success_payload_does_not_merge_content(self):
        event = AgentJournalEvent(
            session_id="sess01",
            type="subagent_dispatch",
            message="bad successful event",
            payload={"subagent_dispatch": {
                "task_id": "should_not_merge",
                "summary": "should not appear",
                "observations": "not a list",
                "success": True,
                "blocked": False,
            }},
        )
        result = merge_journal_subagent_findings([event])
        assert result.summary == ""
        assert result.source_task_ids == []
        assert result.observations == []

    def test_merge_journal_findings_roundtrip_via_store(self, tmp_path):
        store = AgentJournalStore(tmp_path)
        store.record_subagent_dispatch(
            "testses010",
            step=1,
            message="dispatched",
            dispatch_summary={
                "task_id": "abc",
                "task": "check",
                "scope": "src/",
                "max_steps": 1,
                "summary": "All good",
                "observations": ["saw config.py"],
                "files_inspected": ["config.py"],
                "blocked_actions": [],
                "errors": [],
                "success": True,
                "blocked": False,
            },
        )
        events = store.read("testses010")
        result = merge_journal_subagent_findings(events)
        assert result.summary == "All good"
        assert "abc" in result.source_task_ids
        assert "saw config.py" in result.observations


class TestJournalAdapterBlockedExclusion:
    def test_blocked_events_excluded_from_content(self):
        events = [
            AgentJournalEvent(
                session_id="s",
                type="subagent_dispatch",
                message="m",
                payload={"subagent_dispatch": {
                    "task_id": "blocked_task",
                    "summary": "blocked summary",
                    "observations": ["secret"],
                    "files_inspected": ["hidden.py"],
                    "errors": ["permission denied"],
                    "blocked": True,
                    "success": False,
                }},
            )
        ]
        merged = merge_journal_subagent_findings(events)
        assert "blocked summary" not in merged.summary
        assert "secret" not in merged.observations
        assert "hidden.py" not in merged.files_inspected
        assert "permission denied" in merged.errors
        assert "blocked_task" in merged.blocked_task_ids
        assert "blocked_task" not in merged.source_task_ids

    def test_mixed_successful_and_blocked_events(self):
        events = [
            AgentJournalEvent(
                session_id="s",
                type="subagent_dispatch",
                message="m",
                payload={"subagent_dispatch": {
                    "task_id": "ok_task",
                    "summary": "good summary",
                    "observations": ["good obs"],
                    "files_inspected": ["ok.py"],
                    "errors": [],
                    "blocked": False,
                    "success": True,
                }},
            ),
            AgentJournalEvent(
                session_id="s",
                type="subagent_dispatch",
                message="m2",
                payload={"subagent_dispatch": {
                    "task_id": "blocked_task",
                    "summary": "bad summary",
                    "observations": ["bad obs"],
                    "files_inspected": [],
                    "errors": ["network denied"],
                    "blocked": True,
                    "success": False,
                }},
            ),
        ]
        merged = merge_journal_subagent_findings(events)
        assert merged.summary == "good summary"
        assert "good obs" in merged.observations
        assert "bad obs" not in merged.observations
        assert "ok.py" in merged.files_inspected
        assert "ok_task" in merged.source_task_ids
        assert "blocked_task" in merged.blocked_task_ids
        assert "network denied" in merged.errors


# ── v2.2.6: AgentLoop — merged context inclusion ─────────────────────────────


class TestAgentLoopSubagentFindingsInContext:
    """Verify the loop enriches choose_tool context with merged subagent findings."""

    def _make_loop_with_subagent_intent(self, tmp_path, monkeypatch, captured_contexts):
        from safecode.agent.schemas import AgentToolIntentResponse, AgentPlanResponse
        from safecode.agent.tools import ToolIntent

        def fake_plan(self_llm, goal, context):
            return AgentPlanResponse(type="plan", goal=goal, steps=["Subagent step", "Read step"])

        def fake_choose_tool(self_llm, goal, context):
            captured_contexts.append(dict(context))
            return AgentToolIntentResponse(
                type="tool_intent",
                intent=ToolIntent(
                    type="subagent",
                    task_id="ctx_test",
                    description="Inspect config",
                    input_json={"task": "Inspect config", "scope": "src/", "max_steps": 1},
                ),
            )

        monkeypatch.setattr("safecode.llm.mock.MockLLMClient.plan", fake_plan)
        monkeypatch.setattr("safecode.llm.mock.MockLLMClient.choose_tool", fake_choose_tool)
        return AgentLoop(tmp_path)

    def test_first_step_has_no_subagent_findings_key(self, tmp_path, monkeypatch):
        """Before any dispatch, subagent_findings should not appear in context."""
        captured: list[dict] = []
        loop = self._make_loop_with_subagent_intent(tmp_path, monkeypatch, captured)
        loop.step(goal="Check project")
        assert len(captured) >= 1
        # First step: no prior dispatches journaled yet
        assert "subagent_findings" not in captured[0]

    def test_second_step_context_includes_subagent_findings(self, tmp_path, monkeypatch):
        """After a successful dispatch, the next step's context must include subagent_findings."""
        captured: list[dict] = []
        loop = self._make_loop_with_subagent_intent(tmp_path, monkeypatch, captured)
        loop.step(goal="Check project")
        loop.step()
        # Second step should have subagent_findings injected
        assert len(captured) >= 2
        second_context = captured[1]
        assert "subagent_findings" in second_context
        findings = second_context["subagent_findings"]
        assert isinstance(findings["source_task_ids"], list)
        assert isinstance(findings["observations"], list)

    def test_subagent_findings_content_matches_dispatch(self, tmp_path, monkeypatch):
        """subagent_findings in context must reflect the actual dispatch journal event."""
        captured: list[dict] = []
        loop = self._make_loop_with_subagent_intent(tmp_path, monkeypatch, captured)
        loop.step(goal="Inspect project")
        loop.step()
        second = captured[1]
        findings = second.get("subagent_findings", {})
        # The successful dispatch must appear in source_task_ids
        assert len(findings.get("source_task_ids", [])) >= 1

    def test_blocked_dispatch_does_not_add_findings_content(self, tmp_path, monkeypatch):
        """A blocked dispatch must not inject findings content into context."""
        from safecode.agent.schemas import AgentToolIntentResponse, AgentPlanResponse
        from safecode.agent.tools import ToolIntent

        captured: list[dict] = []

        def fake_plan(self_llm, goal, context):
            return AgentPlanResponse(type="plan", goal=goal, steps=["Step A", "Step B"])

        def fake_choose_tool(self_llm, goal, context):
            captured.append(dict(context))
            return AgentToolIntentResponse(
                type="tool_intent",
                intent=ToolIntent(
                    type="subagent",
                    task_id="blocked_ctx",
                    description="blocked",
                    input_json={"task": "bad", "scope": "src/", "max_steps": 99},  # invalid → blocked
                ),
            )

        monkeypatch.setattr("safecode.llm.mock.MockLLMClient.plan", fake_plan)
        monkeypatch.setattr("safecode.llm.mock.MockLLMClient.choose_tool", fake_choose_tool)

        loop = AgentLoop(tmp_path)
        loop.step(goal="test blocked")
        loop.step()

        assert len(captured) >= 2
        second = captured[1]
        findings = second.get("subagent_findings", {})
        # Blocked finding must not contribute to source_task_ids content
        assert "source_task_ids" not in findings or len(findings.get("source_task_ids", [])) == 0

    def test_enrich_fails_closed_on_invalid_session_id(self, tmp_path):
        """_enrich_with_subagent_findings must not crash on an invalid session id."""
        loop = AgentLoop(tmp_path)
        ctx = {"files": ["a.py"]}
        result = loop._enrich_with_subagent_findings("invalid session id!!!", ctx)
        # Context unchanged and no exception raised
        assert "files" in result
        assert "subagent_findings" not in result
