"""Agent contract tests for v2.0.0."""

from __future__ import annotations

import pytest

from safecode.agent.schemas import (
    AgentPlanResponse,
    AgentStopForUserResponse,
    AgentToolIntentResponse,
    parse_agent_contract_response,
)
from safecode.agent.tools import ToolIntentRouter
from safecode.llm.mock import MockLLMClient
from safecode.llm.openai_client import OpenAICompatibleLLMClient


def test_parse_plan_response_from_json():
    response = parse_agent_contract_response(
        '{"type":"plan","goal":"fix tests","steps":["inspect failure","patch code"]}'
    )

    assert isinstance(response, AgentPlanResponse)
    assert response.goal == "fix tests"
    assert response.steps == ["inspect failure", "patch code"]


def test_parse_tool_intent_response_from_fenced_json():
    response = parse_agent_contract_response(
        """```json
{"type":"tool_intent","intent":{"type":"read","target":"README.md","description":"inspect docs"}}
```"""
    )

    assert isinstance(response, AgentToolIntentResponse)
    routed = ToolIntentRouter().route(response.intent.model_dump())
    assert routed.route == "context.read"
    assert routed.executable_now is True


def test_parse_stop_for_user_response():
    response = parse_agent_contract_response(
        {
            "type": "stop_for_user",
            "reason": "needs_scope",
            "message": "Which package should I edit?",
        }
    )

    assert isinstance(response, AgentStopForUserResponse)
    assert response.requires_approval is True


def test_unknown_contract_type_fails_closed():
    with pytest.raises(ValueError, match="Invalid agent contract response"):
        parse_agent_contract_response({"type": "run_anything", "command": "rm -rf /"})


def test_contract_json_must_be_object():
    with pytest.raises(ValueError, match="must be an object"):
        parse_agent_contract_response('["not","an","object"]')


def test_mock_client_returns_structured_plan_and_tool_intent():
    client = MockLLMClient()

    plan = client.plan("make the CLI usable", {"files": ["README.md"]})
    tool_choice = client.choose_tool("make the CLI usable", {"target": "README.md"})

    assert plan.type == "plan"
    assert len(plan.steps) >= 1
    assert isinstance(tool_choice, AgentToolIntentResponse)
    assert tool_choice.intent.type == "read"
    assert ToolIntentRouter().route(tool_choice.intent.model_dump()).route == "context.read"


def test_openai_client_structured_methods_validate_json_without_network(monkeypatch):
    client = OpenAICompatibleLLMClient.__new__(OpenAICompatibleLLMClient)

    def fake_chat(messages):
        if "response type must be plan" in messages[0]["content"]:
            return '{"type":"plan","goal":"ship","steps":["inspect","route"]}'
        return '{"type":"tool_intent","intent":{"type":"read","target":"pyproject.toml"}}'

    monkeypatch.setattr(client, "_chat", fake_chat)

    assert client.plan("ship", {}).steps == ["inspect", "route"]
    assert client.choose_tool("ship", {}).intent.target == "pyproject.toml"
