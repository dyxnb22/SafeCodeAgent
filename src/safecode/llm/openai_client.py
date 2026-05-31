"""Minimal OpenAI-compatible LLM client.

The client only returns text. Patch text is still parsed and validated by the
SafeCode runtime before any file write can happen.
"""

import json
import os
import urllib.error
import urllib.request

from safecode.agent.schemas import (
    AgentAnswer,
    AgentError,
    AgentPatchResponse,
    AgentPlanResponse,
    AgentStopForUserResponse,
    AgentToolIntentResponse,
    parse_agent_contract_response,
)
from safecode.agent.prompts import SYSTEM_PROMPT
from safecode.config import SafeCodeConfig
from safecode.sandbox.network import NetworkPolicy


class OpenAICompatibleLLMClient:
    """Call an OpenAI-compatible chat completions endpoint."""

    def __init__(self, config: SafeCodeConfig) -> None:
        NetworkPolicy(config).assert_allowed(config.llm.base_url)
        self.model = config.llm.model
        self.base_url = config.llm.base_url
        self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("SAFECODE_LLM_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY or SAFECODE_LLM_API_KEY is required for real LLM mode.")

    def ask(self, question: str, context: dict) -> AgentAnswer:
        """Answer a read-only question."""
        content = self._chat(
            [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\nAnswer read-only project questions."},
                {"role": "user", "content": f"Question: {question}\nContext: {json.dumps(context)[:12000]}"},
            ]
        )
        return AgentAnswer(content=content)

    def plan(self, goal: str, context: dict) -> AgentPlanResponse:
        """Return a structured plan for a user goal."""
        response = self._chat_agent_json(
            [
                {"role": "system", "content": self._contract_prompt("plan")},
                {"role": "user", "content": f"Goal: {goal}\nContext: {json.dumps(context)[:12000]}"},
            ]
        )
        if not isinstance(response, AgentPlanResponse):
            raise ValueError(f"Expected plan response, got {response.type}.")
        return response

    def choose_tool(self, goal: str, context: dict) -> AgentToolIntentResponse | AgentStopForUserResponse:
        """Return the next structured tool intent or a user stop."""
        response = self._chat_agent_json(
            [
                {"role": "system", "content": self._contract_prompt("tool_intent or stop_for_user")},
                {"role": "user", "content": f"Goal: {goal}\nContext: {json.dumps(context)[:12000]}"},
            ]
        )
        if not isinstance(response, (AgentToolIntentResponse, AgentStopForUserResponse)):
            raise ValueError(f"Expected tool_intent or stop_for_user response, got {response.type}.")
        return response

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        """Return patch text, leaving parsing and validation to SafeCode."""
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        f"{SYSTEM_PROMPT}\nReturn only a SafeCode patch proposal using *** Begin Patch, "
                        "*** Update File, SEARCH, REPLACE, and *** End Patch. Do not explain."
                    ),
                },
                {"role": "user", "content": f"Task: {task}\nContext: {json.dumps(context)[:12000]}"},
            ]
        )
        return AgentPatchResponse(patch_text=content, explanation="OpenAI-compatible patch response.")

    def _chat_agent_json(
        self, messages: list[dict[str, str]]
    ) -> (
        AgentAnswer
        | AgentPlanResponse
        | AgentToolIntentResponse
        | AgentPatchResponse
        | AgentStopForUserResponse
        | AgentError
    ):
        return parse_agent_contract_response(self._chat(messages))

    def _contract_prompt(self, expected_type: str) -> str:
        return (
            f"{SYSTEM_PROMPT}\nReturn exactly one JSON object and no prose. "
            f"The response type must be {expected_type}. Supported response shapes: "
            '{"type":"answer","content":"..."}, '
            '{"type":"plan","goal":"...","steps":["..."]}, '
            '{"type":"tool_intent","intent":{"type":"read","target":"...","description":"..."},"rationale":"..."}, '
            '{"type":"patch","patch_text":"*** Begin Patch\\n...\\n*** End Patch","explanation":"..."}, '
            '{"type":"stop_for_user","reason":"...","message":"...","requires_approval":true}.'
        )

    def _chat(self, messages: list[dict[str, str]]) -> str:
        payload = json.dumps({"model": self.model, "messages": messages, "temperature": 0}).encode("utf-8")
        request = urllib.request.Request(
            self.base_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc
        return data["choices"][0]["message"]["content"]
