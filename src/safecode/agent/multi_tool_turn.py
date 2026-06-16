"""Multi-tool turn runner for the native tool protocol (v4.22.0+, EXPERIMENTAL).

A "turn" is a sequence of native tool calls the model emits before generating
a final response. The runner:
  - Collects NativeToolCall responses from the model.
  - Dispatches each call through NativeToolDispatcher.
  - Feeds tool results back as context blocks for the next call.
  - Stops when the model emits `answer`, `stop_for_user`, or `stop_for_approval`.
  - Caps at max_turn_tools calls per turn (default 20).

v5.7.0: added ``dispatch_parallel`` for read-only tool calls.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from safecode.agent.native_tools import NativeToolCall, NativeToolResult
from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.context.redactor import redact_secrets

_MAX_TURN_TOOLS = 20
_CAP_HIT_REASON = "per_turn_tool_cap"

# v5.7.0: tool names that are never dispatched in parallel.
_WRITE_TOOL_NAMES = frozenset({
    "edit_file", "write_file", "run_command",
    "github_create_pr", "github_push_branch",
    "mcp.propose_write",
    "sandbox.propose", "sandbox.execute",
})


@dataclass
class TurnToolCallRecord:
    """Record of one tool call within a turn."""

    call_id: str
    tool_name: str
    input_summary: str  # redacted summary, not raw input
    status: str
    output_snippet: str  # first 200 chars of output, redacted


@dataclass
class MultiToolTurnResult:
    """Result of one multi-tool turn."""

    tool_calls: list[TurnToolCallRecord] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    stopped_reason: str = "completed"  # "completed", "cap_hit", "stop_for_user", "error"
    final_response: str = ""
    cap_hit: bool = False

    def context_block(self) -> str:
        """Render all tool results as a compact context string for the next prompt."""
        return "\n".join(self.observations)


class MultiToolTurnRunner:
    """Run a multi-tool turn: dispatch tool calls until the model emits a final response.

    Usage::

        runner = MultiToolTurnRunner(dispatcher, max_turn_tools=20)
        result = runner.run(tool_calls_from_model, llm_call_fn=None)
    """

    def __init__(self, dispatcher: NativeToolDispatcher, max_turn_tools: int = _MAX_TURN_TOOLS) -> None:
        self.dispatcher = dispatcher
        self.max_turn_tools = max_turn_tools

    def dispatch_calls(self, calls: list[NativeToolCall]) -> MultiToolTurnResult:
        """Dispatch a list of native tool calls (serial)."""
        result = MultiToolTurnResult()

        for call in calls:
            if len(result.tool_calls) >= self.max_turn_tools:
                result.cap_hit = True
                result.stopped_reason = _CAP_HIT_REASON
                break

            tool_result = self.dispatcher.dispatch(call)
            observation = redact_secrets(tool_result.to_context_block())
            result.observations.append(observation)

            input_summary = redact_secrets(str(call.input)[:100])
            output_snippet = redact_secrets((tool_result.output or tool_result.error or "")[:200])

            result.tool_calls.append(TurnToolCallRecord(
                call_id=call.call_id,
                tool_name=call.tool_name,
                input_summary=input_summary,
                status=tool_result.status,
                output_snippet=output_snippet,
            ))

        if not result.cap_hit:
            result.stopped_reason = "completed"

        return result

    def dispatch_parallel(
        self,
        calls: list[NativeToolCall],
        *,
        max_workers: int = 3,
    ) -> MultiToolTurnResult:
        """Dispatch read-only native tool calls in parallel.

        Write-classified tool names raise ``ValueError`` — they are never
        dispatched in parallel. Results are merged with stable ordering
        (sorted by original index) for deterministic audit logs. Each result
        is individually redacted.

        Safety invariants (v5.7.0):
        - Only read-only tool calls are dispatched in parallel.
        - Errors in one worker do not crash other workers (isolated via
          ``ThreadPoolExecutor`` as_completed).
        - The caller is responsible for propagating ``CancellationToken``.
        """
        if not calls:
            return MultiToolTurnResult()

        for c in calls:
            if c.tool_name in _WRITE_TOOL_NAMES:
                raise ValueError(
                    f"Write tool {c.tool_name!r} cannot be dispatched in parallel. "
                    f"Use dispatch_calls() instead."
                )

        result = MultiToolTurnResult()

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            fut_map = {
                pool.submit(self.dispatcher.dispatch, call): (i, call)
                for i, call in enumerate(calls)
            }

            indexed_results: list[tuple[int, NativeToolResult, NativeToolCall]] = []

            for future in as_completed(fut_map):
                idx, call = fut_map[future]
                try:
                    tool_result = future.result()
                except Exception as exc:
                    tool_result = NativeToolResult(
                        tool_name=call.tool_name,
                        call_id=call.call_id,
                        status="error",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                indexed_results.append((idx, tool_result, call))

        # Stable ordering by original call index
        indexed_results.sort(key=lambda t: t[0])

        for _idx, tool_result, call in indexed_results:
            observation = redact_secrets(tool_result.to_context_block())
            result.observations.append(observation)

            input_summary = redact_secrets(str(call.input)[:100])
            output_snippet = redact_secrets(
                (tool_result.output or tool_result.error or "")[:200]
            )

            result.tool_calls.append(TurnToolCallRecord(
                call_id=call.call_id,
                tool_name=call.tool_name,
                input_summary=input_summary,
                status=tool_result.status,
                output_snippet=output_snippet,
            ))

        result.stopped_reason = "completed"
        return result

    def run_turn(
        self,
        initial_calls: list[NativeToolCall],
        *,
        llm_next_fn=None,
        context: dict | None = None,
    ) -> MultiToolTurnResult:
        """Run a full turn: dispatch calls, optionally ask model for next action.

        Args:
            initial_calls: First batch of native tool calls from the model.
            llm_next_fn: Optional callable(observations_text, context) -> list[NativeToolCall] | None.
                         When provided, the runner feeds tool results back to the model and
                         continues with more calls until the model returns None (done) or the
                         cap is reached. When None, just dispatches the initial_calls once.
            context: Optional context dict passed to llm_next_fn.
        """
        all_calls = list(initial_calls)
        all_results = MultiToolTurnResult()

        while all_calls:
            if len(all_results.tool_calls) >= self.max_turn_tools:
                all_results.cap_hit = True
                all_results.stopped_reason = _CAP_HIT_REASON
                break

            remaining_cap = self.max_turn_tools - len(all_results.tool_calls)
            more_than_cap = len(all_calls) > remaining_cap
            batch = all_calls[:remaining_cap]
            batch_result = self.dispatch_calls(batch)

            all_results.tool_calls.extend(batch_result.tool_calls)
            all_results.observations.extend(batch_result.observations)

            if batch_result.cap_hit or more_than_cap:
                all_results.cap_hit = True
                all_results.stopped_reason = _CAP_HIT_REASON
                break

            if llm_next_fn is not None:
                obs_text = "\n".join(batch_result.observations)
                next_calls = llm_next_fn(obs_text, context or {})
                if not next_calls:
                    all_results.stopped_reason = "completed"
                    break
                all_calls = list(next_calls)
            else:
                all_calls = []
                all_results.stopped_reason = "completed"

        return all_results

    def identity_sequence(self, calls: list[NativeToolCall]) -> tuple[str, ...]:
        """Return a hashable identity for a sequence of tool calls (for stuck-loop detection)."""
        return tuple(f"{c.tool_name}:{sorted(c.input.items())}" for c in calls)
