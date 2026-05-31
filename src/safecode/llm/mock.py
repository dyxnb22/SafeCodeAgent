"""Deterministic mock LLM client for local development and tests."""

from safecode.agent.schemas import (
    AgentAnswer,
    AgentPatchResponse,
    AgentPlanResponse,
    AgentToolIntentResponse,
)
from safecode.agent.tools import ToolIntent


class MockLLMClient:
    """Return stable responses so the patch workflow can be tested locally."""

    def ask(self, question: str, context: dict) -> AgentAnswer:
        return AgentAnswer(content="SafeCode Agent is a safety-first terminal coding assistant.")

    def plan(self, goal: str, context: dict) -> AgentPlanResponse:
        return AgentPlanResponse(
            goal=goal,
            steps=[
                "Inspect the current project context.",
                "Choose the safest next tool intent.",
                "Stop before any write or command that needs approval.",
            ],
        )

    def choose_tool(self, goal: str, context: dict) -> AgentToolIntentResponse:
        target = context.get("target") or "project_context"
        return AgentToolIntentResponse(
            intent=ToolIntent(
                type="read",
                target=target,
                description=f"Inspect context for: {goal}",
            ),
            rationale="Mock client always starts with a read-only inspection.",
        )

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        files = set(context.get("files", []))
        if "app/main.py" in files:
            return self._fastapi_health_patch()
        return self._readme_status_patch()

    def _readme_status_patch(self) -> AgentPatchResponse:
        """Return the root README status patch used by v0.1.2 examples."""
        search = (
            "This repository currently contains the project framework only. "
            "The implementation should be added step by step after reviewing each module boundary."
        )
        replace = (
            "This repository currently contains the SafeCode Agent v0.1 framework. "
            "Implementation should continue in small reviewed steps."
        )
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

    def _fastapi_health_patch(self) -> AgentPatchResponse:
        """Return a deterministic FastAPI /health endpoint patch."""
        search = '''@app.get("/")
def root() -> dict[str, str]:
    """Return a tiny demo response."""
    return {"message": "hello from fastapi demo"}'''
        replace = '''@app.get("/")
def root() -> dict[str, str]:
    """Return a tiny demo response."""
    return {"message": "hello from fastapi demo"}


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return a basic health check response."""
    return {"status": "ok"}'''
        return AgentPatchResponse(
            patch_text=f"""*** Begin Patch
*** Update File: app/main.py
@@
SEARCH:
{search}
REPLACE:
{replace}
*** End Patch""",
            explanation="Mock patch response for the FastAPI v0.1.5 demo.",
        )
