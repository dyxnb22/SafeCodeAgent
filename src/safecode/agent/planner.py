"""Diff planner: predict touched files before patch generation and compare to actual scope."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from safecode.patch.models import PatchProposal

# Matches file path tokens: optional directory segments then filename.ext.
# \b ensures we start only at a word boundary; (?<![:/.]) rejects URL components
# (: from http:, / from path separators, . from domain dots like "example.com/path").
_FILE_PATH_RE = re.compile(
    r"(?<![:/.])\b"
    r"((?:[\w][\w.-]*/)*[\w][\w.-]*"
    r"\.(?:py|md|txt|json|toml|yaml|yml|js|ts|sh|cfg|ini|html|css|go|rs|java|rb))",
    re.IGNORECASE,
)


class DiffPlan(BaseModel):
    """Predicted file scope for a task, captured before patch generation."""

    task: str
    predicted_files: list[str]


class DiffScopeResult(BaseModel):
    """Comparison of predicted vs. actual patch scope.

    status values:
    - ``no_prediction``: no files could be extracted from the task; comparison skipped.
    - ``match``: actual touched files equal predicted files exactly.
    - ``within_scope``: actual is a strict subset of predicted (some predicted files untouched).
    - ``extra_files``: actual contains at least one file not in the predicted set; warning emitted.
    """

    plan: DiffPlan
    actual_files: list[str]
    status: Literal["no_prediction", "match", "within_scope", "extra_files"]
    extra_files: list[str]
    warning: str | None = None


class DiffPlanner:
    """Extract predicted file scope from task text and compare to an actual patch."""

    def predict(self, task: str, context_hint: str = "") -> DiffPlan:
        """Return a DiffPlan by scanning task and optional context_hint for file paths."""
        combined = f"{task}\n{context_hint}"
        matches = _FILE_PATH_RE.findall(combined)
        seen: set[str] = set()
        unique: list[str] = []
        for m in matches:
            if m not in seen:
                seen.add(m)
                unique.append(m)
        return DiffPlan(task=task, predicted_files=unique)

    def compare(self, plan: DiffPlan, proposal: PatchProposal) -> DiffScopeResult:
        """Compare a DiffPlan to the files actually touched by a PatchProposal.

        Does not block or modify the proposal; only returns metadata and an
        optional warning string that callers may surface or log.
        """
        seen_actual: set[str] = set()
        actual: list[str] = []
        for block in proposal.blocks:
            path = block.file_path.as_posix()
            if path not in seen_actual:
                seen_actual.add(path)
                actual.append(path)

        if not plan.predicted_files:
            return DiffScopeResult(
                plan=plan,
                actual_files=actual,
                status="no_prediction",
                extra_files=[],
                warning=None,
            )

        predicted_set = set(plan.predicted_files)
        extra = [f for f in actual if f not in predicted_set]

        if extra:
            warning = (
                f"Patch scope warning: {len(extra)} file(s) outside predicted scope: "
                + ", ".join(extra)
            )
            return DiffScopeResult(
                plan=plan,
                actual_files=actual,
                status="extra_files",
                extra_files=extra,
                warning=warning,
            )

        status = "match" if set(actual) == predicted_set else "within_scope"
        return DiffScopeResult(
            plan=plan,
            actual_files=actual,
            status=status,
            extra_files=[],
            warning=None,
        )
