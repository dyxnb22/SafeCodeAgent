"""Deterministic merge policy for subagent findings (v2.2.5)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SubagentFinding:
    """Structured findings from one dispatched subagent investigation."""

    task_id: str
    summary: str
    observations: list[str] = field(default_factory=list)
    files_inspected: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    blocked: bool = False
    success: bool = False


@dataclass(frozen=True)
class MergedSubagentContext:
    """Merged findings from multiple subagent investigations."""

    summary: str
    observations: list[str] = field(default_factory=list)
    files_inspected: list[str] = field(default_factory=list)
    source_task_ids: list[str] = field(default_factory=list)
    blocked_task_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def merge_subagent_findings(
    findings: list[SubagentFinding],
    max_observations: int = 20,
    max_files: int = 50,
) -> MergedSubagentContext:
    """Merge a list of SubagentFinding into a single MergedSubagentContext.

    Rules (in input order):
    - Only successful findings contribute to summary/observations/files_inspected.
    - Observations and files are deduplicated preserving first occurrence.
    - Errors and blocked_task_ids are collected from failed/blocked findings.
    - max_observations and max_files caps are applied after dedup.
    - Never raises on empty input or malformed/empty fields.
    """
    if not findings:
        return MergedSubagentContext(summary="")

    source_task_ids: list[str] = []
    blocked_task_ids: list[str] = []
    errors: list[str] = []
    summary_parts: list[str] = []
    seen_observations: dict[str, None] = {}
    seen_files: dict[str, None] = {}

    for f in findings:
        task_id = f.task_id or ""

        if f.blocked or not f.success:
            if task_id:
                blocked_task_ids.append(task_id)
            for err in (f.errors or []):
                if err:
                    errors.append(err)
            continue

        if task_id:
            source_task_ids.append(task_id)

        if f.summary:
            summary_parts.append(f.summary)

        for obs in (f.observations or []):
            if obs and obs not in seen_observations:
                seen_observations[obs] = None

        for path in (f.files_inspected or []):
            if path and path not in seen_files:
                seen_files[path] = None

    all_observations = list(seen_observations.keys())[:max_observations]
    all_files = list(seen_files.keys())[:max_files]

    summary = "; ".join(summary_parts) if summary_parts else ""

    return MergedSubagentContext(
        summary=summary,
        observations=all_observations,
        files_inspected=all_files,
        source_task_ids=source_task_ids,
        blocked_task_ids=blocked_task_ids,
        errors=errors,
    )
