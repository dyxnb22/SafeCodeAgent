"""Base protocol for LLM clients."""

from typing import Protocol

from safecode.agent.schemas import (
    AgentAnswer,
    AgentPatchResponse,
    AgentPlanResponse,
    AgentStopForUserResponse,
    AgentToolIntentResponse,
)


class LLMClient(Protocol):
    """Interface used by the orchestrator."""

    def ask(self, question: str, context: dict) -> AgentAnswer:
        """Answer a read-only question."""

    def plan(self, goal: str, context: dict) -> AgentPlanResponse:
        """Return a structured plan for a user goal."""

    def choose_tool(self, goal: str, context: dict) -> AgentToolIntentResponse | AgentStopForUserResponse:
        """Return the next structured tool intent or a user stop."""

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        """Return a patch proposal without writing files."""
