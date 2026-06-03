"""Convert subagent_dispatch journal events to SubagentFinding (v2.2.6 / v2.8.7 / v2.9.6)."""

from __future__ import annotations

import warnings

from pydantic import ValidationError

from safecode.context.redactor import redact_secrets
from safecode.state.journal import AgentJournalEvent
from safecode.subagents.merge_policy import (
    MergedSubagentContext,
    SubagentFinding,
    merge_subagent_findings,
)
from safecode.subagents.payload import (
    SUPPORTED_PAYLOAD_VERSIONS,
    SubagentDispatchPayload,
)


def _event_to_finding(event: AgentJournalEvent) -> SubagentFinding | None:
    """Convert one subagent_dispatch event payload to SubagentFinding.

    Uses typed, tolerant loading via SubagentDispatchPayload (v2.9.6).
    Old journals (without payload_version) parse with default version 1.
    Unsupported future versions and malformed payloads are skipped with a
    RuntimeWarning rather than crashing. Never raises.
    """
    try:
        raw_outer = event.payload.get("subagent_dispatch")
        if not isinstance(raw_outer, dict):
            return None

        try:
            typed = SubagentDispatchPayload.model_validate(raw_outer)
        except (ValidationError, Exception) as exc:
            warnings.warn(
                f"subagent_dispatch payload failed typed parsing (session={event.session_id}, "
                f"event_id={event.event_id}): {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            return None

        if typed.payload_version not in SUPPORTED_PAYLOAD_VERSIONS:
            warnings.warn(
                f"subagent_dispatch payload version {typed.payload_version} is not supported "
                f"(session={event.session_id}); skipping event.",
                RuntimeWarning,
                stacklevel=2,
            )
            return None

        blocked = typed.blocked
        success = typed.success
        task_id = typed.task_id

        # Producer-side redaction: secrets are removed at the journal boundary
        # before merged context can reach agent loop prompts (v2.8.7).
        observations = [redact_secrets(o) for o in typed.observations if isinstance(o, str)]
        files_inspected = [str(f) for f in typed.files_inspected]
        errors = [redact_secrets(e) for e in typed.errors if isinstance(e, str)]
        # v2 fields are read but not surfaced in SubagentFinding (synthesis
        # is handled separately by synthesize_findings in the loop).

        return SubagentFinding(
            task_id=task_id,
            summary=redact_secrets(typed.summary),
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

    Malformed payloads are skipped with a RuntimeWarning. Never raises.
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
