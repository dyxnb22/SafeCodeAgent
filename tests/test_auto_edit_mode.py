"""Tests for v5.1.0 auto-edit mode, P1 native_step wiring, and P2 prompt caching."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.loop import AgentLoop
from safecode.agent.native_tools import NativeToolCall, NativeToolResult, NativeToolSpec
from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.multi_tool_turn import MultiToolTurnRunner
from safecode.agent.schemas import AgentNativeToolCallResponse, AgentStopForUserResponse, RecoverableContractFailure
from safecode.llm.cost import TokenUsage


# ---------------------------------------------------------------------------
# TokenUsage cache fields (P2)
# ---------------------------------------------------------------------------

class TestCacheTokenFields:
    def test_token_usage_has_cache_fields(self):
        u = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15,
                       cache_read_tokens=100, cache_creation_tokens=50)
        assert u.cache_read_tokens == 100
        assert u.cache_creation_tokens == 50

    def test_token_usage_cache_fields_default_zero(self):
        u = TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
        assert u.cache_read_tokens == 0
        assert u.cache_creation_tokens == 0

    def test_token_usage_addition_sums_cache_fields(self):
        a = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15,
                       cache_read_tokens=100, cache_creation_tokens=50)
        b = TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30,
                       cache_read_tokens=200, cache_creation_tokens=0)
        total = a + b
        assert total.cache_read_tokens == 300
        assert total.cache_creation_tokens == 50

    def test_token_usage_as_dict_includes_cache_fields(self):
        u = TokenUsage(cache_read_tokens=5, cache_creation_tokens=3)
        d = u.as_dict()
        assert d["cache_read_tokens"] == 5
        assert d["cache_creation_tokens"] == 3

    def test_session_cost_accumulator_persists_cache_fields(self, tmp_path):
        from safecode.llm.cost import SessionCostAccumulator
        sac_dir = tmp_path / ".sac"
        acc = SessionCostAccumulator(sac_dir, "sess-001")
        usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15,
                           cache_read_tokens=100, cache_creation_tokens=20)
        acc.record(usage)
        loaded = acc.load()
        assert loaded is not None
        assert loaded.cache_read_tokens == 100
        assert loaded.cache_creation_tokens == 20


# ---------------------------------------------------------------------------
# CheckpointMetadata.session_id (v5.1.0)
# ---------------------------------------------------------------------------

class TestCheckpointSessionId:
    def test_checkpoint_metadata_has_session_id(self):
        from safecode.checkpoint.models import CheckpointMetadata, CheckpointFileOperation
        meta = CheckpointMetadata(
            checkpoint_id="cp-001",
            task="test",
            patch_id="p-001",
            created_at="2026-01-01T00:00:00Z",
            file_operations=[],
            session_id="sess-abc",
        )
        assert meta.session_id == "sess-abc"

    def test_checkpoint_metadata_session_id_defaults_none(self):
        from safecode.checkpoint.models import CheckpointMetadata
        meta = CheckpointMetadata(
            checkpoint_id="cp-002",
            task="test",
            patch_id="p-002",
            created_at="2026-01-01T00:00:00Z",
            file_operations=[],
        )
        assert meta.session_id is None


# ---------------------------------------------------------------------------
# AgentLoop auto_edit attribute (v5.1.0)
# ---------------------------------------------------------------------------

class TestAgentLoopAutoEdit:
    def test_agent_loop_default_auto_edit_false(self, tmp_path):
        loop = AgentLoop(tmp_path)
        assert loop.auto_edit is False

    def test_agent_loop_auto_edit_true(self, tmp_path):
        loop = AgentLoop(tmp_path, auto_edit=True)
        assert loop.auto_edit is True

    def test_agent_loop_native_write_count_starts_zero(self, tmp_path):
        loop = AgentLoop(tmp_path)
        assert loop._native_write_count == 0


# ---------------------------------------------------------------------------
# _build_dispatcher registers write tools with approved=auto_edit (v5.1.0)
# ---------------------------------------------------------------------------

class TestBuildDispatcher:
    def test_build_dispatcher_registers_read_tools(self, tmp_path):
        loop = AgentLoop(tmp_path)
        dispatcher = loop._build_dispatcher()
        names = {s.name for s in dispatcher.specs()}
        assert "read_file" in names
        assert "list_files" in names

    def test_build_dispatcher_registers_write_tools(self, tmp_path):
        loop = AgentLoop(tmp_path)
        dispatcher = loop._build_dispatcher()
        names = {s.name for s in dispatcher.specs()}
        assert "edit_file" in names
        assert "write_file" in names

    def test_write_tool_blocked_when_auto_edit_false(self, tmp_path):
        (tmp_path / "hello.py").write_text("x = 1\n")
        loop = AgentLoop(tmp_path, auto_edit=False)
        dispatcher = loop._build_dispatcher()
        call = NativeToolCall(
            tool_name="edit_file",
            input={"path": "hello.py", "old_string": "x = 1", "new_string": "x = 2"},
            call_id="c1",
        )
        result = dispatcher.dispatch(call)
        assert result.status == "blocked"

    def test_write_tool_executes_when_auto_edit_true(self, tmp_path):
        (tmp_path / "hello.py").write_text("x = 1\n")
        loop = AgentLoop(tmp_path, auto_edit=True)
        dispatcher = loop._build_dispatcher()
        call = NativeToolCall(
            tool_name="edit_file",
            input={"path": "hello.py", "old_string": "x = 1\n", "new_string": "x = 2\n"},
            call_id="c1",
        )
        result = dispatcher.dispatch(call)
        assert result.status == "success"
        assert (tmp_path / "hello.py").read_text() == "x = 2\n"

    def test_run_command_still_registered(self, tmp_path):
        loop = AgentLoop(tmp_path)
        dispatcher = loop._build_dispatcher()
        names = {s.name for s in dispatcher.specs()}
        assert "run_command" in names


# ---------------------------------------------------------------------------
# native_step() falls back to step() when LLM has no choose_tool_native (v5.1.0)
# ---------------------------------------------------------------------------

class TestNativeStepFallback:
    def test_native_step_falls_back_to_step_when_no_native_support(self, tmp_path):
        """LLM without choose_tool_native → native_step() calls step()."""
        mock_llm = MagicMock(spec=[])  # No choose_tool_native attribute
        loop = AgentLoop(tmp_path, llm_client=mock_llm)

        step_result = MagicMock()
        with patch.object(loop, "step", return_value=step_result) as mock_step:
            result = loop.native_step("test goal")
        mock_step.assert_called_once_with("test goal")
        assert result is step_result


# ---------------------------------------------------------------------------
# native_step() with choose_tool_native returning stop_for_user (v5.1.0)
# ---------------------------------------------------------------------------

class TestNativeStepStopForUser:
    def test_native_step_stop_for_user_stops_loop(self, tmp_path):
        stop_response = AgentStopForUserResponse(
            reason="done",
            message="All done!",
            requires_approval=False,
        )
        mock_llm = MagicMock()
        mock_llm.choose_tool_native.return_value = stop_response
        mock_llm.plan.return_value = MagicMock(steps=["step1"])
        mock_llm.choose_tool.return_value = stop_response

        loop = AgentLoop(tmp_path, llm_client=mock_llm)
        result = loop.native_step("test goal")
        assert result.stopped_for_approval is True
        assert "All done!" in result.observation


# ---------------------------------------------------------------------------
# native_step() with native tool calls dispatched via MultiToolTurnRunner (v5.1.0)
# ---------------------------------------------------------------------------

class TestNativeStepDispatch:
    def test_native_step_dispatches_tool_calls(self, tmp_path):
        """choose_tool_native returns tool calls → MultiToolTurnRunner dispatches them."""
        tool_responses = [
            AgentNativeToolCallResponse(tool_name="read_file", input={"path": "foo.py"}, call_id="c1"),
        ]
        mock_llm = MagicMock()
        mock_llm.choose_tool_native.side_effect = [tool_responses, AgentStopForUserResponse(
            reason="done", message="done", requires_approval=False
        )]
        mock_llm.plan.return_value = MagicMock(steps=["read the file"])

        (tmp_path / "foo.py").write_text("hello\n")
        loop = AgentLoop(tmp_path, llm_client=mock_llm)
        result = loop.native_step("read foo.py")
        # Should have dispatched the read call and produced an observation
        assert result.state is not None
        assert "read_file" in result.observation or len(result.observation) > 0

    def test_native_step_recoverable_failure_retried(self, tmp_path):
        """RCF on first call → retried; second RCF → permanent failure recorded."""
        rcf = RecoverableContractFailure(step=0, method="choose_tool_native", message="bad output")
        mock_llm = MagicMock()
        mock_llm.choose_tool_native.return_value = rcf
        mock_llm.plan.return_value = MagicMock(steps=["step1"])

        loop = AgentLoop(tmp_path, llm_client=mock_llm)
        result = loop.native_step("test goal")
        # After two failures, observation should mention the failure
        assert "contract failure" in result.observation.lower() or "native" in result.observation.lower()
        assert result.stopped_for_approval is False


# ---------------------------------------------------------------------------
# Auto-edit file count guard (v5.1.0)
# ---------------------------------------------------------------------------

class TestFileCountGuard:
    def test_file_count_guard_triggers_at_10_writes(self, tmp_path):
        """When _native_write_count >= 10 in auto_edit mode, native_step pauses."""
        mock_llm = MagicMock()
        mock_llm.plan.return_value = MagicMock(steps=["write files"])
        # Set up a stop_for_user so native_step starts, but the guard fires first
        mock_llm.choose_tool_native.return_value = AgentStopForUserResponse(
            reason="done", message="done", requires_approval=False
        )

        loop = AgentLoop(tmp_path, llm_client=mock_llm, auto_edit=True)
        loop._native_write_count = 10  # Simulate already at guard limit

        result = loop.native_step("write files")
        assert result.stopped_for_approval is True
        assert "file" in result.observation.lower()


# ---------------------------------------------------------------------------
# Anthropic prompt caching sends cache_control (P2)
# ---------------------------------------------------------------------------

class TestAnthropicPromptCaching:
    def test_messages_payload_includes_cache_control(self):
        import json
        from safecode.llm.anthropic_client import AnthropicLLMClient
        from safecode.config import SafeCodeConfig

        config = SafeCodeConfig()
        config.llm.base_url = "https://api.anthropic.com/v1/messages"
        config.llm.api_key = "test-key"

        captured_payload: list[dict] = []

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def read(self):
                return json.dumps({"content": [{"type": "text", "text": "hi"}], "usage": {}}).encode()

        def fake_urlopen(req, timeout=None):
            body = json.loads(req.data.decode())
            captured_payload.append(body)
            return FakeResponse()

        with patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"):
            client = AnthropicLLMClient(config)

        with patch("urllib.request.urlopen", fake_urlopen):
            client._messages(system="sys prompt", user="user msg")

        assert len(captured_payload) == 1
        payload = captured_payload[0]
        # System must be a list with cache_control
        assert isinstance(payload["system"], list)
        assert payload["system"][0]["cache_control"] == {"type": "ephemeral"}
        # First user message must have cache_control
        msgs = payload["messages"]
        assert isinstance(msgs[0]["content"], list)
        assert msgs[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
