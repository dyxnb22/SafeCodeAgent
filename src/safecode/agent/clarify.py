"""Pre-task disambiguation for AgentLoop (v6.8.0).

Detects ambiguous goals before the first step and returns clarifying questions
so the user can provide specifics before the agent starts editing files.

Safety:
- Never writes files.
- Falls back gracefully (no clarification) on LLM error.
- Can be bypassed with no_clarify=True for automation/CI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Heuristic pre-filter — skip LLM if goal is already specific enough
# ---------------------------------------------------------------------------

# Strong specificity signals: file path, line number, function call, test name
_SPECIFIC_PATTERNS = [
    re.compile(r"\b\w[\w/\\]+\.\w{1,6}\b"),      # path with extension
    re.compile(r"\bline\s+\d+\b", re.IGNORECASE),  # "line 42"
    re.compile(r"\bdef\s+\w+|\bclass\s+\w+"),       # "def foo" / "class Bar"
    re.compile(r"\btest_\w+\b"),                    # test function name
    re.compile(r"\bfrom\s+\S+\s+import\b"),         # import statement fragment
    re.compile(r"\b(TypeError|ValueError|KeyError|AttributeError|ImportError)"),
]

# Vague goals that are very short and contain only generic verbs
_VAGUE_VERBS = frozenset({"fix", "update", "improve", "refactor", "clean", "add", "remove", "change"})


def _is_specific_enough(goal: str) -> bool:
    """Return True if the goal is concrete enough to skip clarification."""
    if len(goal) > 120:
        return True
    for pattern in _SPECIFIC_PATTERNS:
        if pattern.search(goal):
            return True
    # Short goal with only vague verbs — ask for clarification
    words = {w.lower().strip(".,!?") for w in goal.split()}
    meaningful = words - _VAGUE_VERBS - {"the", "a", "an", "it", "this", "that", "some", "all"}
    return len(meaningful) >= 3


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClarificationResult:
    needs_clarification: bool
    questions: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""

    @classmethod
    def skip(cls) -> "ClarificationResult":
        return cls(needs_clarification=False)

    @classmethod
    def ask(cls, questions: list[str], reason: str = "") -> "ClarificationResult":
        return cls(needs_clarification=True, questions=tuple(questions), reason=reason)


# ---------------------------------------------------------------------------
# LLM-powered ambiguity detection
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a concise code assistant. Determine whether the user's task description "
    "is specific enough to act on, or needs clarification.\n\n"
    "Respond with a JSON object with two fields:\n"
    '  "needs_clarification": true/false\n'
    '  "questions": ["question1", "question2"] (empty list if no clarification needed)\n\n'
    "Ask at most 2 short questions. Be conservative — only ask when genuinely ambiguous."
)


def detect_ambiguity(goal: str, llm_client: object) -> ClarificationResult:
    """Return a ClarificationResult using the LLM client.

    Falls back to ClarificationResult.skip() on any error.
    """
    import json

    if _is_specific_enough(goal):
        return ClarificationResult.skip()

    # Only use LLM if client has an ask() method
    if not hasattr(llm_client, "ask"):
        return ClarificationResult.skip()

    prompt = f'Task: "{goal}"\n\nIs this specific enough to act on, or do you need clarification?'
    try:
        raw = llm_client.ask(prompt, {"system": _SYSTEM_PROMPT})  # type: ignore[union-attr]
        # Extract JSON — LLM may wrap in markdown code fences
        json_match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if not json_match:
            return ClarificationResult.skip()
        data = json.loads(json_match.group())
        needs = bool(data.get("needs_clarification", False))
        questions = [str(q) for q in data.get("questions", []) if q][:2]
        if needs and questions:
            return ClarificationResult.ask(questions, reason="llm_detected_ambiguity")
        return ClarificationResult.skip()
    except Exception:
        return ClarificationResult.skip()
