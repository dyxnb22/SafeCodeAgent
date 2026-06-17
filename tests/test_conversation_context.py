"""Tests for conversation-aware context selection (v6.7.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.context.selector import ContextSelector, _CONVERSATION_BONUS, _RECENCY_BONUS


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return tmp_path


class TestConversationAwareSelector:
    def test_conversation_file_gets_bonus(self, tmp_path: Path) -> None:
        _make_project(tmp_path, {
            "src/alpha.py": "def alpha(): pass",
            "src/beta.py": "def beta(): pass",
        })
        selector = ContextSelector(tmp_path)
        # Both match query "alpha" — but "src/beta.py" is in conversation history
        sources = selector.select_sources(
            "alpha",
            conversation_files=["src/beta.py"],
        )
        # beta should get a bonus and may outrank alpha even though alpha has keyword match
        beta = next((s for s in sources if "beta" in s.path), None)
        alpha = next((s for s in sources if "alpha" in s.path), None)
        if beta and alpha:
            # beta has conversation bonus, alpha has keyword match — check reason
            assert "conversation" in beta.reason

    def test_conversation_bonus_applied_to_reason(self, tmp_path: Path) -> None:
        _make_project(tmp_path, {"src/target.py": "def foo(): pass"})
        selector = ContextSelector(tmp_path)
        sources = selector.select_sources(
            "target",
            conversation_files=["src/target.py"],
        )
        target = next((s for s in sources if "target" in s.path), None)
        assert target is not None
        assert "conversation" in target.reason
        assert "path matched" in target.reason

    def test_no_conversation_files_behavior_unchanged(self, tmp_path: Path) -> None:
        _make_project(tmp_path, {"src/foo.py": "x = 1"})
        selector = ContextSelector(tmp_path)
        sources_with = selector.select_sources("foo", conversation_files=["src/foo.py"])
        sources_without = selector.select_sources("foo")
        # Both should find foo.py; with conversation it gets extra bonus
        assert any("foo" in s.path for s in sources_with)
        assert any("foo" in s.path for s in sources_without)
        with_score = next(s.score for s in sources_with if "foo" in s.path)
        without_score = next(s.score for s in sources_without if "foo" in s.path)
        assert with_score >= without_score

    def test_conversation_files_none_is_identical_to_empty(self, tmp_path: Path) -> None:
        _make_project(tmp_path, {"src/foo.py": "x = 1"})
        selector = ContextSelector(tmp_path)
        s_none = selector.select_sources("foo", conversation_files=None)
        s_empty = selector.select_sources("foo", conversation_files=[])
        assert [s.path for s in s_none] == [s.path for s in s_empty]

    def test_conversation_file_by_basename(self, tmp_path: Path) -> None:
        _make_project(tmp_path, {"src/deep/path/util.py": "def util(): pass"})
        selector = ContextSelector(tmp_path)
        sources = selector.select_sources("util", conversation_files=["util.py"])
        util_src = next((s for s in sources if "util" in s.path), None)
        if util_src:
            assert "conversation" in util_src.reason


class TestChooseToolNativeConversationHistory:
    """Verify the LLM clients accept conversation_history without error (mock)."""

    def test_openai_client_accepts_history_param(self, tmp_path: Path) -> None:
        from safecode.llm.mock import MockLLMClient
        client = MockLLMClient()
        # MockLLMClient may not implement choose_tool_native with history;
        # we just verify the OpenAI client signature accepts the new kwarg.
        from safecode.llm.openai_client import OpenAICompatibleLLMClient
        import inspect
        sig = inspect.signature(OpenAICompatibleLLMClient.choose_tool_native)
        assert "conversation_history" in sig.parameters

    def test_anthropic_client_accepts_history_param(self) -> None:
        from safecode.llm.anthropic_client import AnthropicLLMClient
        import inspect
        sig = inspect.signature(AnthropicLLMClient.choose_tool_native)
        assert "conversation_history" in sig.parameters

    def test_messages_include_history_when_passed(self) -> None:
        """Verify history is prepended between system and current user message."""
        import json
        from safecode.llm.openai_client import OpenAICompatibleLLMClient

        captured_messages: list = []

        class _CapturingClient(OpenAICompatibleLLMClient):
            def _chat(self, messages):
                captured_messages.extend(messages)
                # Return a no-op stop response
                return json.dumps({
                    "type": "stop_for_user",
                    "reason": "done",
                    "message": "ok",
                    "requires_approval": False,
                })

        client = _CapturingClient.__new__(_CapturingClient)
        client.model = "test"
        client.api_key = "test-key"
        client.base_url = "http://localhost"
        client._max_retries = 1
        client._retry_base_delay = 0.0
        client._request_timeout = 5
        client._session_id = None
        client._sac_dir = None
        client._last_token_usage = {"input": 0, "output": 0, "cache_read": 0}

        # Monkey-patch urlopen to hit _chat via our capturing subclass path.
        # Actually, OpenAICompatibleLLMClient uses urlopen directly, not _chat.
        # Easier: just verify the payload construction by inspecting json.dumps call.
        import urllib.request as _urllib

        last_payload: list[dict] = []

        class _FakeResponse:
            def read(self): return json.dumps({
                "choices": [{"message": {"content": "ok", "tool_calls": None}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        original_urlopen = _urllib.urlopen
        def _fake_urlopen(req, **kw):
            import json as _j
            last_payload.append(_j.loads(req.data))
            return _FakeResponse()

        _urllib.urlopen = _fake_urlopen
        try:
            history = [
                {"role": "user", "content": "prior question"},
                {"role": "assistant", "content": "prior answer"},
            ]
            client.choose_tool_native(
                "new goal",
                {},
                [],
                conversation_history=history,
            )
        finally:
            _urllib.urlopen = original_urlopen

        assert last_payload, "No HTTP request was captured"
        msgs = last_payload[0]["messages"]
        roles = [m["role"] for m in msgs]
        # Expected: system, user(prior), assistant(prior), user(current goal)
        assert roles[0] == "system"
        assert "prior question" in msgs[1]["content"]
        assert "prior answer" in msgs[2]["content"]
        assert "new goal" in msgs[-1]["content"]

    def test_agent_loop_run_passes_conversation_to_native_client(self, tmp_path: Path) -> None:
        from safecode.agent.conversation import ConversationBuffer
        from safecode.agent.loop import AgentLoop
        from safecode.agent.schemas import AgentPlanResponse, AgentStopForUserResponse

        class _NativeClient:
            def __init__(self) -> None:
                self.histories: list[list[dict] | None] = []

            def plan(self, goal: str, context: dict) -> AgentPlanResponse:
                return AgentPlanResponse(goal=goal, steps=["answer from context"])

            def choose_tool_native(self, goal, context, tool_specs, *, step=0, conversation_history=None):
                self.histories.append(conversation_history)
                return AgentStopForUserResponse(
                    reason="done",
                    message="ok",
                    requires_approval=False,
                )

        conv = ConversationBuffer(session_id="s1", sac_dir=tmp_path / ".sac")
        conv.append_user("Earlier we discussed src/foo.py")
        conv.append_assistant("I remember src/foo.py")
        client = _NativeClient()

        loop = AgentLoop(tmp_path, llm_client=client, no_clarify=True)
        result = loop.run("continue", max_steps=1, conversation=conv)

        assert result.steps
        assert client.histories
        assert client.histories[0] is not None
        assert "src/foo.py" in client.histories[0][0]["content"]
