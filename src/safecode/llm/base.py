"""Base protocol for LLM clients."""

from typing import Protocol

from safecode.agent.schemas import AgentAnswer, AgentPatchResponse


class LLMClient(Protocol):
    """Interface used by the orchestrator."""

    def ask(self, question: str, context: dict) -> AgentAnswer:
        """Answer a read-only question."""

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        """Return a patch proposal without writing files."""
