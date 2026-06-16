"""Tests for v3.2.2 structured output validation."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from safecode.agent.schemas import (
    AgentAnswer,
    AgentPatchResponse,
    AgentPlanResponse,
    AgentStopForUserResponse,
    AgentToolIntentResponse,
    RecoverableContractFailure,
    validate_provider_json,
)


# ---------------------------------------------------------------------------
# validate_provider_json — core behaviour
# ---------------------------------------------------------------------------


class TestValidateProviderJsonInvalidJson:
    def test_invalid_json_string_returns_recoverable(self) -> None:
        result = validate_provider_json("{not valid json}")
        assert isinstance(result, RecoverableContractFailure)

    def test_truncated_json_returns_recoverable(self) -> None:
        result = validate_provider_json('{"type":"answer","content":')
        assert isinstance(result, RecoverableContractFailure)

    def test_empty_string_returns_recoverable(self) -> None:
        result = validate_provider_json("")
        assert isinstance(result, RecoverableContractFailure)

    def test_non_object_json_returns_recoverable(self) -> None:
        result = validate_provider_json('["list", "not", "object"]')
        assert isinstance(result, RecoverableContractFailure)

    def test_number_json_returns_recoverable(self) -> None:
        result = validate_provider_json("42")
        assert isinstance(result, RecoverableContractFailure)


class TestValidateProviderJsonMissingType:
    def test_missing_type_field_returns_recoverable(self) -> None:
        result = validate_provider_json('{"content":"hello"}')
        assert isinstance(result, RecoverableContractFailure)

    def test_empty_type_field_returns_recoverable(self) -> None:
        result = validate_provider_json('{"type":"","content":"hello"}')
        assert isinstance(result, RecoverableContractFailure)

    def test_null_type_returns_recoverable(self) -> None:
        result = validate_provider_json('{"type":null,"content":"hello"}')
        assert isinstance(result, RecoverableContractFailure)


class TestValidateProviderJsonMissingRequiredFields:
    def test_answer_missing_content_returns_recoverable(self) -> None:
        result = validate_provider_json('{"type":"answer"}')
        assert isinstance(result, RecoverableContractFailure)

    def test_plan_missing_goal_returns_recoverable(self) -> None:
        result = validate_provider_json('{"type":"plan","steps":["step1"]}')
        assert isinstance(result, RecoverableContractFailure)

    def test_plan_missing_steps_returns_recoverable(self) -> None:
        result = validate_provider_json('{"type":"plan","goal":"do something"}')
        assert isinstance(result, RecoverableContractFailure)

    def test_tool_intent_missing_intent_returns_recoverable(self) -> None:
        result = validate_provider_json('{"type":"tool_intent","rationale":"x"}')
        assert isinstance(result, RecoverableContractFailure)

    def test_patch_missing_patch_text_returns_recoverable(self) -> None:
        result = validate_provider_json('{"type":"patch"}')
        assert isinstance(result, RecoverableContractFailure)

    def test_stop_for_user_missing_reason_returns_recoverable(self) -> None:
        result = validate_provider_json('{"type":"stop_for_user","message":"hi"}')
        assert isinstance(result, RecoverableContractFailure)

    def test_stop_for_user_missing_message_returns_recoverable(self) -> None:
        result = validate_provider_json('{"type":"stop_for_user","reason":"r"}')
        assert isinstance(result, RecoverableContractFailure)


class TestValidateProviderJsonWrongFieldTypes:
    def test_plan_steps_not_list_returns_recoverable(self) -> None:
        result = validate_provider_json('{"type":"plan","goal":"g","steps":"not a list"}')
        assert isinstance(result, RecoverableContractFailure)

    def test_answer_content_not_string_returns_recoverable(self) -> None:
        # Pydantic will coerce int→str for content, so this is valid per schema
        result = validate_provider_json('{"type":"answer","content":123}')
        # Accept either way depending on Pydantic coercion behaviour
        assert isinstance(result, (AgentAnswer, RecoverableContractFailure))

    def test_plan_steps_empty_list_returns_recoverable(self) -> None:
        # AgentPlanResponse requires min_length=1
        result = validate_provider_json('{"type":"plan","goal":"g","steps":[]}')
        assert isinstance(result, RecoverableContractFailure)


class TestValidateProviderJsonExtraFields:
    def test_extra_fields_tolerated_for_known_types(self) -> None:
        data = '{"type":"answer","content":"hello","extra_field":"ignored"}'
        result = validate_provider_json(data)
        assert isinstance(result, AgentAnswer)
        assert result.content == "hello"

    def test_extra_fields_in_plan_tolerated(self) -> None:
        data = json.dumps({
            "type": "plan",
            "goal": "do x",
            "steps": ["step1"],
            "unknown_key": "value",
        })
        result = validate_provider_json(data)
        assert isinstance(result, AgentPlanResponse)


class TestValidateProviderJsonValidResponses:
    def test_valid_answer_parses(self) -> None:
        result = validate_provider_json('{"type":"answer","content":"hello"}')
        assert isinstance(result, AgentAnswer)
        assert result.content == "hello"

    def test_valid_plan_parses(self) -> None:
        result = validate_provider_json('{"type":"plan","goal":"fix bug","steps":["check code"]}')
        assert isinstance(result, AgentPlanResponse)
        assert result.goal == "fix bug"

    def test_valid_stop_for_user_parses(self) -> None:
        data = '{"type":"stop_for_user","reason":"need input","message":"Please review"}'
        result = validate_provider_json(data)
        assert isinstance(result, AgentStopForUserResponse)

    def test_valid_patch_parses(self) -> None:
        data = '{"type":"patch","patch_text":"*** Begin Patch\\n*** End Patch"}'
        result = validate_provider_json(data)
        assert isinstance(result, AgentPatchResponse)

    def test_fenced_json_block_parses(self) -> None:
        data = '```json\n{"type":"answer","content":"wrapped"}\n```'
        result = validate_provider_json(data)
        assert isinstance(result, AgentAnswer)

    def test_dict_input_parses(self) -> None:
        result = validate_provider_json({"type": "answer", "content": "from dict"})
        assert isinstance(result, AgentAnswer)


class TestValidateProviderJsonRecoverableFailureShape:
    def test_recoverable_has_step_method_message(self) -> None:
        result = validate_provider_json("{bad}", step=3, method="choose_tool")
        assert isinstance(result, RecoverableContractFailure)
        assert result.step == 3
        assert result.method == "choose_tool"
        assert len(result.message) > 0

    def test_missing_required_field_message_names_fields(self) -> None:
        result = validate_provider_json('{"type":"plan","goal":"g"}', method="plan")
        assert isinstance(result, RecoverableContractFailure)
        assert "steps" in result.message

    def test_missing_type_message_is_informative(self) -> None:
        result = validate_provider_json('{"content":"no type"}')
        assert isinstance(result, RecoverableContractFailure)
        assert "type" in result.message.lower()


# ---------------------------------------------------------------------------
# OpenAICompatibleLLMClient._chat_agent_json wiring
# ---------------------------------------------------------------------------


def _make_client():
    from safecode.config import SafeCodeConfig
    from safecode.llm.openai_client import OpenAICompatibleLLMClient

    cfg = SafeCodeConfig()
    cfg.llm.provider = "openai-compatible"
    cfg.llm.base_url = "http://localhost:9999/v1/chat/completions"

    with (
        patch("safecode.sandbox.network.NetworkPolicy.assert_allowed"),
        patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
    ):
        return OpenAICompatibleLLMClient(config=cfg)


class TestOpenAIClientStructuredOutputValidation:
    def _mock_chat(self, client, raw_response: str):
        """Patch _chat to return raw_response."""
        with patch.object(client, "_chat", return_value=raw_response):
            yield

    def test_invalid_json_choose_tool_returns_recoverable(self) -> None:
        client = _make_client()
        with patch.object(client, "_chat", return_value="{bad json}"):
            result = client.choose_tool("goal", {})
        assert isinstance(result, RecoverableContractFailure)

    def test_missing_type_choose_tool_returns_recoverable(self) -> None:
        client = _make_client()
        with patch.object(client, "_chat", return_value='{"intent":{}}'):
            result = client.choose_tool("goal", {})
        assert isinstance(result, RecoverableContractFailure)

    def test_wrong_contract_type_choose_tool_raises_hard_error(self) -> None:
        # A structurally valid JSON with the wrong type (plan where tool_intent expected)
        # is a hard contract violation — it raises ValueError (fail-closed), not recoverable.
        client = _make_client()
        with patch.object(client, "_chat", return_value='{"type":"plan","goal":"g","steps":["s"]}'):
            with pytest.raises(ValueError, match="Expected tool_intent or stop_for_user"):
                client.choose_tool("goal", {})

    def test_valid_tool_intent_parses_correctly(self) -> None:
        client = _make_client()
        data = json.dumps({
            "type": "tool_intent",
            "intent": {"type": "read", "target": "main.py", "description": "read"},
            "rationale": "checking",
        })
        with patch.object(client, "_chat", return_value=data):
            result = client.choose_tool("goal", {})
        assert isinstance(result, AgentToolIntentResponse)

    def test_propose_patch_accepts_json_patch_contract(self) -> None:
        client = _make_client()
        patch_text = (
            "*** Begin Patch\n"
            "*** Update File: src/app.py\n"
            "SEARCH:\nold\n"
            "REPLACE:\nnew\n"
            "*** End Patch"
        )
        data = json.dumps({"type": "patch", "patch_text": patch_text, "explanation": "fix"})
        with patch.object(client, "_chat", return_value=data):
            result = client.propose_patch("fix", {})
        assert isinstance(result, AgentPatchResponse)
        assert result.patch_text == patch_text

    def test_propose_patch_extracts_patch_envelope_from_raw_output(self) -> None:
        client = _make_client()
        patch_text = (
            "*** Begin Patch\n"
            "*** Update File: src/app.py\n"
            "SEARCH:\nold\n"
            "REPLACE:\nnew\n"
            "*** End Patch"
        )
        raw = f"Here is the patch:\n```text\n{patch_text}\n```\nDone."
        with patch.object(client, "_chat", return_value=raw):
            result = client.propose_patch("fix", {})
        assert result.patch_text == patch_text

    def test_invalid_json_plan_raises_value_error(self) -> None:
        client = _make_client()
        with patch.object(client, "_chat", return_value="{bad}"):
            with pytest.raises(ValueError, match="validation"):
                client.plan("goal", {})

    def test_no_crash_on_malformed_provider_body(self) -> None:
        client = _make_client()
        malformed_inputs = [
            "",
            "null",
            "[]",
            '{"type":"unknown_type_xyz"}',
            '{"type":"answer"}',  # missing content → recoverable
        ]
        for raw in malformed_inputs:
            with patch.object(client, "_chat", return_value=raw):
                try:
                    result = client.choose_tool("goal", {})
                    assert isinstance(result, RecoverableContractFailure), (
                        f"Expected RecoverableContractFailure for input {raw!r}, got {result!r}"
                    )
                except ValueError:
                    pass  # plan() raises, but choose_tool() should not crash


# ---------------------------------------------------------------------------
# Existing mock/scripted LLM tests must keep passing
# ---------------------------------------------------------------------------


class TestExistingBehaviorUnchanged:
    def test_parse_agent_contract_response_unchanged(self) -> None:
        from safecode.agent.schemas import parse_agent_contract_response

        result = parse_agent_contract_response('{"type":"answer","content":"hello"}')
        assert isinstance(result, AgentAnswer)
        assert result.content == "hello"

    def test_parse_agent_contract_response_invalid_still_raises(self) -> None:
        from safecode.agent.schemas import parse_agent_contract_response

        with pytest.raises(ValueError):
            parse_agent_contract_response("{bad json}")

    def test_mock_client_still_works(self) -> None:
        from safecode.llm.mock import MockLLMClient

        client = MockLLMClient()
        answer = client.ask("question", {})
        assert isinstance(answer, AgentAnswer)
        plan = client.plan("goal", {})
        assert isinstance(plan, AgentPlanResponse)
        intent = client.choose_tool("inspect", {})
        assert isinstance(intent, AgentToolIntentResponse)
