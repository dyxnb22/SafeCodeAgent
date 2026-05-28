"""Minimal OpenAI-compatible LLM client.

The client only returns text. Patch text is still parsed and validated by the
SafeCode runtime before any file write can happen.
"""

import json
import os
import urllib.error
import urllib.request

from safecode.agent.schemas import AgentAnswer, AgentPatchResponse
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
                {"role": "system", "content": "You are SafeCode Agent. Answer read-only project questions."},
                {"role": "user", "content": f"Question: {question}\nContext: {json.dumps(context)[:12000]}"},
            ]
        )
        return AgentAnswer(content=content)

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        """Return patch text, leaving parsing and validation to SafeCode."""
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Return only a SafeCode patch proposal using *** Begin Patch, "
                        "*** Update File, SEARCH, REPLACE, and *** End Patch. Do not explain."
                    ),
                },
                {"role": "user", "content": f"Task: {task}\nContext: {json.dumps(context)[:12000]}"},
            ]
        )
        return AgentPatchResponse(patch_text=content, explanation="OpenAI-compatible patch response.")

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
