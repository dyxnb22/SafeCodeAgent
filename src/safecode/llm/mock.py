"""Deterministic mock LLM client for v0.1 development and tests."""

from safecode.agent.schemas import AgentAnswer, AgentPatchResponse


class MockLLMClient:
    """Return stable responses so the patch workflow can be tested locally."""

    def ask(self, question: str, context: dict) -> AgentAnswer:
        return AgentAnswer(content="SafeCode Agent is a safety-first terminal coding assistant.")

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        search = "This repository currently contains the project framework only. The implementation should be added step by step after reviewing each module boundary."
        replace = "This repository currently contains the SafeCode Agent v0.1 framework. Implementation should continue in small reviewed steps."
        return AgentPatchResponse(
            patch_text=f"""*** Begin Patch
*** Update File: README.md
@@
SEARCH:
{search}
REPLACE:
{replace}
*** End Patch""",
            explanation="Mock patch response for the v0.1.2 edit workflow.",
        )
