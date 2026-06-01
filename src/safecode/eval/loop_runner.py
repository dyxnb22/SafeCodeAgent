"""Agent loop eval mode with scripted LLM responses (v2.7.7).

This module provides:
- ``ScriptedLLMClient`` — a test-only LLM stub driven by explicit scripted
  sequences, not keyword matching. Contract violations fail closed.
- ``LoopEvalFixture`` — a lightweight in-memory eval fixture for loop-mode evals.
- ``LoopEvalResult`` — a typed, snapshot-friendly result object.
- ``LoopModeEvalRunner`` — runs the agent loop in a tmp workspace with a
  scripted LLM; no real network calls are made.
- ``default_loop_fixtures`` — two realistic scripted fixtures (docs-edit and
  python-function-fix).
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from safecode.agent.loop import AgentLoop
from safecode.agent.schemas import (
    AgentAnswer,
    AgentPatchResponse,
    AgentPlanResponse,
    AgentStopForUserResponse,
    AgentToolIntentResponse,
)
from safecode.agent.tools import ToolIntent


# ── Contract violation ────────────────────────────────────────────────────


@dataclass(frozen=True)
class LLMContractViolation:
    """Raised (as a value, not an exception) when scripted sequence is exhausted."""

    step: int
    method: str
    message: str


# ── Scripted LLM client ───────────────────────────────────────────────────


@dataclass(frozen=True)
class ScriptedStep:
    """One scripted agent step: a tool choice and an optional patch response."""

    tool_choice: AgentToolIntentResponse | AgentStopForUserResponse
    patch_response: AgentPatchResponse | None = None
    plan: AgentPlanResponse | None = None


class ScriptedLLMClient:
    """Deterministic LLM stub driven by explicit scripted sequences.

    When the script is exhausted or a contract is violated the client returns a
    ``LLMContractViolation`` descriptor. Callers that receive this must treat it
    as a hard failure (fail closed).
    """

    def __init__(self, steps: list[ScriptedStep], plan: AgentPlanResponse | None = None) -> None:
        self._steps = steps
        self._default_plan = plan
        self._step_index = 0
        self.violations: list[LLMContractViolation] = []

    def _violation(self, method: str, msg: str) -> LLMContractViolation:
        v = LLMContractViolation(step=self._step_index, method=method, message=msg)
        self.violations.append(v)
        return v

    def ask(self, question: str, context: dict) -> AgentAnswer:
        return AgentAnswer(content=f"[scripted] read-only answer for: {question[:60]}")

    def plan(self, goal: str, context: dict) -> AgentPlanResponse | LLMContractViolation:
        current = self._step_index
        if current < len(self._steps) and self._steps[current].plan is not None:
            return self._steps[current].plan  # type: ignore[return-value]
        if self._default_plan is not None:
            return self._default_plan
        return AgentPlanResponse(
            goal=goal,
            steps=["Inspect project state.", "Propose patch if needed.", "Stop for approval."],
        )

    def choose_tool(
        self, goal: str, context: dict
    ) -> AgentToolIntentResponse | AgentStopForUserResponse | LLMContractViolation:
        if self._step_index >= len(self._steps):
            return self._violation("choose_tool", f"Script exhausted after {len(self._steps)} step(s).")
        choice = self._steps[self._step_index].tool_choice
        self._step_index += 1
        return choice

    def propose_patch(self, task: str, context: dict) -> AgentPatchResponse | LLMContractViolation:
        idx = self._step_index - 1
        if idx < 0 or idx >= len(self._steps):
            return self._violation("propose_patch", f"propose_patch called outside scripted range (idx={idx}).")
        patch = self._steps[idx].patch_response
        if patch is None:
            return self._violation("propose_patch", f"Step {idx} has no scripted patch response.")
        return patch


# ── Eval fixture and result ───────────────────────────────────────────────


@dataclass(frozen=True)
class LoopEvalFixture:
    """A self-contained agent loop eval case."""

    name: str
    goal: str
    files: dict[str, str]
    scripted_steps: list[ScriptedStep]
    expected_pending_patch: bool = True
    expected_patch_contains: list[str] = field(default_factory=list)


@dataclass
class LoopEvalResult:
    """Result of running one ``LoopEvalFixture``."""

    fixture_name: str
    passed: bool
    failure_reasons: list[str] = field(default_factory=list)
    violations: list[LLMContractViolation] = field(default_factory=list)
    pending_patch_text: str | None = None
    stopped_reason: str = ""

    @property
    def ok(self) -> bool:
        return self.passed and not self.violations


# ── Runner ────────────────────────────────────────────────────────────────


class LoopModeEvalRunner:
    """Run agent loop evals with scripted LLM clients in isolated tmp workspaces."""

    def run_fixture(self, fixture: LoopEvalFixture) -> LoopEvalResult:
        """Run one fixture in a fresh tmp workspace. No real network calls."""
        with tempfile.TemporaryDirectory(prefix="sac-loop-eval-") as tmpdir:
            workspace = Path(tmpdir)
            self._materialise_files(workspace, fixture.files)

            llm_client = ScriptedLLMClient(fixture.scripted_steps)
            loop = AgentLoop(project_root=workspace, llm_client=llm_client)

            run_result = None
            loop_error: str | None = None
            pending_patch_text: str | None = None
            try:
                run_result = loop.run(goal=fixture.goal, max_steps=len(fixture.scripted_steps) + 2)
                # Read pending patch text while workspace still exists.
                pending = run_result.state.pending_action or {}
                pp_path = pending.get("pending_patch_path")
                if pp_path and Path(str(pp_path)).exists():
                    import json as _json
                    raw = _json.loads(Path(str(pp_path)).read_text(encoding="utf-8"))
                    patch_blocks = raw.get("blocks", [])
                    # Reconstruct a plain text representation for assertion checking.
                    pending_patch_text = "\n".join(
                        f"*** Update File: {b.get('file_path', '')}\n{b.get('search', '')}\n{b.get('replace', '')}"
                        for b in patch_blocks
                    )
                    if not pending_patch_text.strip():
                        pending_patch_text = raw.get("task", "") or str(raw)
            except Exception as exc:
                loop_error = f"Loop raised unexpected exception: {type(exc).__name__}: {exc}"

        # Evaluate result after workspace is cleaned up.
        if loop_error or run_result is None:
            return LoopEvalResult(
                fixture_name=fixture.name,
                passed=False,
                failure_reasons=[loop_error or "Loop returned no result."],
                violations=list(llm_client.violations),
                stopped_reason="error",
            )

        result = LoopEvalResult(
            fixture_name=fixture.name,
            passed=True,
            violations=list(llm_client.violations),
            stopped_reason=run_result.stopped_reason,
        )

        if llm_client.violations:
            result.passed = False
            for v in llm_client.violations:
                result.failure_reasons.append(f"LLM contract violation in {v.method}: {v.message}")
            return result

        state = run_result.state
        pending = state.pending_action or {}

        if fixture.expected_pending_patch:
            # Accept: pending_action["type"] == "patch" with a readable pending patch path.
            pending_type = str(pending.get("type", ""))
            pp_path_str = str(pending.get("pending_patch_path", ""))
            patch_text_for_check = pending_patch_text or pp_path_str
            result.pending_patch_text = patch_text_for_check
            if pending_type != "patch" or not pp_path_str:
                result.passed = False
                result.failure_reasons.append(
                    f"Expected a pending patch (type=patch + pending_patch_path) "
                    f"but got type={pending_type!r}, path={pp_path_str!r}"
                )
            else:
                for fragment in fixture.expected_patch_contains:
                    if patch_text_for_check and fragment not in patch_text_for_check:
                        result.passed = False
                        result.failure_reasons.append(
                            f"Pending patch missing expected fragment: {fragment!r}"
                        )

        return result

    def run_all(self, fixtures: list[LoopEvalFixture]) -> list[LoopEvalResult]:
        return [self.run_fixture(f) for f in fixtures]

    @staticmethod
    def _materialise_files(workspace: Path, files: dict[str, str]) -> None:
        for relative, content in files.items():
            target = (workspace / relative).resolve()
            if not str(target).startswith(str(workspace.resolve())):
                raise PermissionError(f"File escapes workspace: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")


# ── Default fixtures ──────────────────────────────────────────────────────


def default_loop_fixtures() -> list[LoopEvalFixture]:
    """Return two realistic scripted loop-mode eval fixtures."""
    return [_docs_edit_fixture(), _python_function_fix_fixture()]


def _docs_edit_fixture() -> LoopEvalFixture:
    """Docs-edit: agent reads then proposes a safety note patch."""
    read_step = ScriptedStep(
        tool_choice=AgentToolIntentResponse(
            intent=ToolIntent(type="read", target="docs/usage.md", description="Inspect usage docs"),
            rationale="Read docs before proposing a change.",
        )
    )
    patch_step = ScriptedStep(
        tool_choice=AgentToolIntentResponse(
            intent=ToolIntent(
                type="patch",
                target="docs/usage.md",
                description="Add a safety note about checkpoint review",
                requires_approval=True,
            ),
            rationale="Propose patch to add safety note.",
        ),
        patch_response=AgentPatchResponse(
            patch_text=(
                "*** Begin Patch\n"
                "*** Update File: docs/usage.md\n"
                "@@\n"
                "SEARCH:\n"
                "Run `sac edit` to propose a change.\n"
                "REPLACE:\n"
                "Run `sac edit` to propose a change.\n"
                "Always review the diff at the checkpoint prompt before applying.\n"
                "*** End Patch"
            ),
            explanation="Scripted safety note addition.",
        ),
    )
    return LoopEvalFixture(
        name="docs-edit",
        goal="Add a safety note about reviewing the diff before applying to docs/usage.md",
        files={
            "docs/usage.md": "# Usage\n\nRun `sac edit` to propose a change.\n",
            ".sac/config.toml": '[llm]\nprovider = "mock"\n',
        },
        scripted_steps=[read_step, patch_step],
        expected_pending_patch=True,
        expected_patch_contains=["Always review the diff", "checkpoint prompt"],
    )


def _python_function_fix_fixture() -> LoopEvalFixture:
    """Python function fix: agent reads then proposes a bug-fix patch."""
    read_step = ScriptedStep(
        tool_choice=AgentToolIntentResponse(
            intent=ToolIntent(type="read", target="src/utils.py", description="Inspect utils module"),
            rationale="Read the broken function before proposing a fix.",
        )
    )
    patch_step = ScriptedStep(
        tool_choice=AgentToolIntentResponse(
            intent=ToolIntent(
                type="patch",
                target="src/utils.py",
                description="Fix multiply to return a * b instead of a - b",
                requires_approval=True,
            ),
            rationale="Propose patch to fix the broken multiply function.",
        ),
        patch_response=AgentPatchResponse(
            patch_text=(
                "*** Begin Patch\n"
                "*** Update File: src/utils.py\n"
                "@@\n"
                "SEARCH:\n"
                "    return a - b\n"
                "REPLACE:\n"
                "    return a * b\n"
                "*** End Patch"
            ),
            explanation="Scripted fix for broken multiply.",
        ),
    )
    return LoopEvalFixture(
        name="python-function-fix",
        goal="Fix the multiply function in src/utils.py to return a * b instead of a - b",
        files={
            "src/utils.py": "def multiply(a: int, b: int) -> int:\n    return a - b\n",
            ".sac/config.toml": '[llm]\nprovider = "mock"\n',
        },
        scripted_steps=[read_step, patch_step],
        expected_pending_patch=True,
        expected_patch_contains=["return a * b", "src/utils.py"],
    )
