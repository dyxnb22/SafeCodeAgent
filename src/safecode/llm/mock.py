"""Deterministic mock LLM client for local development and tests."""

from typing import Any, Iterator

from safecode.agent.schemas import (
    AgentAnswer,
    AgentNativeToolCallResponse,
    AgentPatchResponse,
    AgentPlanResponse,
    AgentStopForUserResponse,
    AgentToolIntentResponse,
    RecoverableContractFailure,
)
from safecode.agent.native_tools import NativeToolCall, NativeToolSpec
from safecode.agent.tools import ToolIntent
from safecode.llm.stream import StreamChunk


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
        if "calculator" in goal.lower():
            return AgentToolIntentResponse(
                intent=ToolIntent(
                    type="patch",
                    target="src/calculator.py",
                    description=f"Propose patch to fix: {goal}",
                    requires_approval=True,
                ),
                rationale="Mock client proposes patch for write-like calculator goal.",
            )
        target = context.get("target") or "project_context"
        return AgentToolIntentResponse(
            intent=ToolIntent(
                type="read",
                target=target,
                description=f"Inspect context for: {goal}",
            ),
            rationale="Mock client always starts with a read-only inspection.",
        )

    def stream_chat(self, messages: list[dict], **kwargs: object) -> Iterator[StreamChunk]:
        """Return mock answer as a single chunk, mimicking a real stream."""
        answer = "SafeCode Agent is a safety-first terminal coding assistant."
        yield StreamChunk(delta=answer, finish_reason="stop")

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse:
        if "calculator" in task.lower():
            return self._calculator_fix_patch()
        files = set(context.get("files", []))
        if "app/main.py" in files:
            return self._fastapi_health_patch()
        if "src/todo_cli/cli.py" in files:
            return self._cli_version_patch()
        if "docs/usage.md" in files:
            return self._docs_review_patch()
        if "src/calculator.py" in files:
            return self._calculator_fix_patch()
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

    def _cli_version_patch(self) -> AgentPatchResponse:
        """Return a deterministic CLI --version patch."""
        search = '''def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo")
    parser.add_argument("item", nargs="?", default="write tests")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print(f"next: {args.item}")
    return 0'''
        replace = '''def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("item", nargs="?", default="write tests")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print("todo 0.1.0")
        return 0
    print(f"next: {args.item}")
    return 0'''
        return AgentPatchResponse(
            patch_text=f"""*** Begin Patch
*** Update File: src/todo_cli/cli.py
@@
SEARCH:
{search}
REPLACE:
{replace}
*** End Patch""",
            explanation="Mock patch response for the CLI version flag demo.",
        )

    def _docs_review_patch(self) -> AgentPatchResponse:
        """Return a deterministic docs-only review guidance patch."""
        search = "Run `sac edit` to create a pending patch, then inspect the diff before applying it."
        replace = (
            "Run `sac edit` to create a pending patch, inspect the diff carefully, "
            "then run `sac apply` only after the checkpoint prompt matches the change you expect."
        )
        return AgentPatchResponse(
            patch_text=f"""*** Begin Patch
*** Update File: docs/usage.md
@@
SEARCH:
{search}
REPLACE:
{replace}
*** End Patch""",
            explanation="Mock patch response for the docs-only demo.",
        )

    def _calculator_fix_patch(self) -> AgentPatchResponse:
        """Return a deterministic failing-test repair patch."""
        search = '''def add(left: int, right: int) -> int:
    """Return the sum of two integers."""
    return left - right + 0'''
        replace = '''def add(left: int, right: int) -> int:
    """Return the sum of two integers."""
    return left + right'''
        return AgentPatchResponse(
            patch_text=f"""*** Begin Patch
*** Update File: src/calculator.py
@@
SEARCH:
{search}
REPLACE:
{replace}
*** End Patch""",
            explanation="Mock patch response for the failing-test repair demo.",
        )


# ---------------------------------------------------------------------------
# ScriptedNativeToolLLMClient — v6.34 native-tool mock coverage
# ---------------------------------------------------------------------------

#: Type for one scripted response from the mock model.
#: - list[NativeToolCall]: model wants to invoke these tools next.
#: - AgentStopForUserResponse: model is done / needs approval.
#: - RecoverableContractFailure: transient failure (loop may retry once).
ScriptedResponse = (
    list[NativeToolCall]
    | AgentStopForUserResponse
    | RecoverableContractFailure
)


class ScriptedNativeToolLLMClient(MockLLMClient):
    """Mock LLM client that drives the native-tool path via a scripted call sequence.

    ``choose_tool_native`` is called once per model "turn" (initial call + each
    follow-up after tool results are fed back).  The ``script`` list maps 1:1
    to those calls in order.

    When the script is exhausted, subsequent calls return a default
    ``AgentStopForUserResponse`` so the loop always terminates cleanly.

    Usage::

        from safecode.agent.native_tools import NativeToolCall
        from safecode.agent.schemas import AgentStopForUserResponse

        script = [
            # Turn 0: model reads a file
            [NativeToolCall(tool_name="read_file", input={"path": "src/foo.py"}, call_id="c1")],
            # Turn 1: after seeing the file, model stops for approval
            AgentStopForUserResponse(reason="patch_ready", message="I will now propose a patch."),
        ]
        client = ScriptedNativeToolLLMClient(script)
        loop = AgentLoop(project_root=tmp_path, llm_client=client)
        result = loop.native_step("fix the bug")
    """

    def __init__(self, script: list[ScriptedResponse]) -> None:
        self._script = list(script)
        self._call_count = 0
        self.recorded_calls: list[dict[str, Any]] = []  # introspection in tests

    def choose_tool_native(
        self,
        goal: str,
        context: dict[str, Any],
        tool_specs: list[NativeToolSpec],
        *,
        step: int = 0,
        conversation_history: list[dict] | None = None,
    ) -> list[AgentNativeToolCallResponse] | AgentStopForUserResponse | RecoverableContractFailure:
        self.recorded_calls.append({
            "goal": goal,
            "step": step,
            "call_index": self._call_count,
            "context_keys": list(context.keys()),
        })

        if self._call_count >= len(self._script):
            # Script exhausted — return a clean stop so the loop always terminates.
            return AgentStopForUserResponse(
                reason="script_exhausted",
                message="ScriptedNativeToolLLMClient: no more scripted responses.",
            )

        response = self._script[self._call_count]
        self._call_count += 1

        if isinstance(response, (AgentStopForUserResponse, RecoverableContractFailure)):
            return response

        # Convert list[NativeToolCall] → list[AgentNativeToolCallResponse]
        return [
            AgentNativeToolCallResponse(
                tool_name=call.tool_name,
                input=call.input,
                call_id=call.call_id or f"scripted_{self._call_count}_{i}",
            )
            for i, call in enumerate(response)
        ]

    @property
    def native_call_count(self) -> int:
        """How many times choose_tool_native was called."""
        return self._call_count
