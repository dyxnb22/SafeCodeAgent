"""Convert subagent_dispatch journal events to SubagentFinding (v2.2.6)."""

from __future__ import annotations

from safecode.state.journal import AgentJournalEvent
from safecode.subagents.merge_policy import (
    MergedSubagentContext,
    SubagentFinding,
    merge_subagent_findings,
)


def _event_to_finding(event: AgentJournalEvent) -> SubagentFinding | None:
    """Convert one subagent_dispatch event payload to SubagentFinding.

    Returns None if the payload is missing or malformed. Never raises.
    """
    try:
        payload = event.payload.get("subagent_dispatch")
        if not isinstance(payload, dict):
            return None
        task_id = str(payload.get("task_id", ""))
        summary = str(payload.get("summary", ""))
        raw_obs = payload.get("observations", [])
        raw_files = payload.get("files_inspected", [])
        raw_errors = payload.get("errors", [])
        if (
            not isinstance(raw_obs, list)
            or not isinstance(raw_files, list)
            or not isinstance(raw_errors, list)
        ):
            return None
        blocked = bool(payload.get("blocked", False))
        success = bool(payload.get("success", False))
        observations = [str(o) for o in raw_obs]
        files_inspected = [str(f) for f in raw_files]
        errors = [str(e) for e in raw_errors]
        return SubagentFinding(
            task_id=task_id,
            summary=summary,
            observations=observations,
            files_inspected=files_inspected,
            errors=errors,
            blocked=blocked,
            success=success,
        )
    except Exception:
        return None


def findings_from_journal_events(events: list[AgentJournalEvent]) -> list[SubagentFinding]:
    """Extract SubagentFinding objects from subagent_dispatch journal events.

    Malformed payloads are silently skipped. Never raises.
    """
    findings: list[SubagentFinding] = []
    for event in events:
        if event.type != "subagent_dispatch":
            continue
        finding = _event_to_finding(event)
        if finding is not None:
            findings.append(finding)
    return findings


def merge_journal_subagent_findings(
    events: list[AgentJournalEvent],
    max_observations: int = 20,
    max_files: int = 50,
) -> MergedSubagentContext:
    """Convert subagent_dispatch journal events to a MergedSubagentContext.

    Never raises.
    """
    findings = findings_from_journal_events(events)
    return merge_subagent_findings(findings, max_observations=max_observations, max_files=max_files)
