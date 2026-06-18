"""Run timeline JSON serializer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from safecode.context.redactor import redact_secrets
from safecode.enterprise.approvals.store import list_requests
from safecode.enterprise.trace.emitter import TraceEmitter, trace_file_path
from safecode.enterprise.trace.events import TraceEvent, TraceEventType
from safecode.enterprise.workflow.checkpoint import load_checkpoint
from safecode.enterprise.workflow.contracts import NodeCost
from safecode.enterprise.workflow.ids import validate_run_id

TIMELINE_SCHEMA_VERSION = 1
TIMELINE_REDACT_EXCERPT_CHARS = 256


class TimelineActor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    roles: list[str] = Field(default_factory=list)


class TimelineNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: str
    started_at: str
    ended_at: str
    duration_ms: int
    summary: str
    events: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, str]] = Field(default_factory=list)


class TimelineCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str
    source_id: str
    source_type: str
    path: str
    start_line: int
    end_line: int
    score: float
    selection_reason: str
    permission_verdict: str
    freshness: str
    hash: str
    text_excerpt: str
    redacted: bool = False


class TimelineToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    tool_category: str
    decision: str
    outcome: str
    duration_ms: int
    cost: NodeCost
    events: list[str] = Field(default_factory=list)


class TimelineApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    action: str
    risk_tier: str
    decision: dict[str, str]
    status: str
    grant_id: str | None = None
    consumed_at: str | None = None
    decision_actor: str | None = None


class TimelineValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ran: bool
    summary: str


class TimelineSafetyInvariants(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_chain_intact: bool = True
    no_unauthorized_mutation: bool = True
    no_policy_block_overridden: bool = True
    no_grant_double_consume: bool = True
    redaction_complete: bool = True


class RunTimeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeline_schema_version: int = TIMELINE_SCHEMA_VERSION
    run_id: str
    tenant_id: str
    task_type: str
    status: str
    actor: TimelineActor
    policy_snapshot_id: str
    summary: str
    started_at: str
    ended_at: str | None
    duration_ms: int
    nodes: list[TimelineNode] = Field(default_factory=list)
    citations: list[TimelineCitation] = Field(default_factory=list)
    tool_calls: list[TimelineToolCall] = Field(default_factory=list)
    approvals: list[TimelineApproval] = Field(default_factory=list)
    validation: TimelineValidation
    proposals: list[dict[str, str]] = Field(default_factory=list)
    costs: dict[str, Any] = Field(default_factory=dict)
    safety_invariants: TimelineSafetyInvariants = Field(default_factory=TimelineSafetyInvariants)
    failures: list[dict[str, str]] = Field(default_factory=list)


def timeline_path(sac_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    return trace_file_path(sac_root, run_id).parent / "timeline.json"


def _redact_excerpt(text: str) -> tuple[str, bool]:
    redacted = redact_secrets(text)
    changed = redacted != text
    if len(redacted) > TIMELINE_REDACT_EXCERPT_CHARS:
        redacted = redacted[:TIMELINE_REDACT_EXCERPT_CHARS] + "…"
        changed = True
    return redacted, changed


def _node_events(events: list[TraceEvent], node_name: str) -> list[str]:
    return [event.event_id for event in events if event.node_id == node_name]


def _duration_ms(started_at: str, ended_at: str) -> int:
    if not started_at or not ended_at:
        return 0
    from datetime import datetime

    start = datetime.fromisoformat(started_at)
    end = datetime.fromisoformat(ended_at)
    return max(0, int((end - start).total_seconds() * 1000))


def build_timeline(sac_root: Path, run_id: str) -> RunTimeline:
    checkpoint = load_checkpoint(sac_root, run_id)
    state = checkpoint.state
    trace_events = TraceEmitter(sac_root, run_id).iter_events()
    approval_requests = list_requests(sac_root, run_id)

    nodes: list[TimelineNode] = []
    for node_name, output in state.node_outputs.items():
        nodes.append(
            TimelineNode(
                name=node_name,
                status=output.status,
                started_at=output.started_at,
                ended_at=output.ended_at,
                duration_ms=_duration_ms(output.started_at, output.ended_at),
                summary=output.summary,
                events=_node_events(trace_events, node_name),
                artifacts=[
                    {"name": artifact.name, "kind": artifact.kind, "ref": artifact.ref}
                    for artifact in output.artifacts
                ],
            )
        )

    citations: list[TimelineCitation] = []
    for citation in state.citations:
        excerpt, redacted = _redact_excerpt(citation.text_excerpt)
        citations.append(
            TimelineCitation(
                citation_id=citation.citation_id,
                source_id=citation.source_id,
                source_type=str(citation.source_type),
                path=citation.path,
                start_line=citation.start_line,
                end_line=citation.end_line,
                score=citation.score,
                selection_reason=citation.selection_reason,
                permission_verdict=citation.permission_verdict,
                freshness=citation.freshness,
                hash=citation.hash,
                text_excerpt=excerpt,
                redacted=redacted,
            )
        )

    tool_calls = [
        TimelineToolCall(
            call_id=item.call_id,
            tool_name=item.tool_name,
            tool_category=item.tool_category,
            decision=item.decision.decision,
            outcome=item.outcome,
            duration_ms=item.cost.latency_ms,
            cost=item.cost,
            events=[
                event.event_id
                for event in trace_events
                if event.type
                in {
                    TraceEventType.tool_proposed,
                    TraceEventType.tool_executed,
                    TraceEventType.tool_blocked,
                }
                and event.payload.get("call_id") == item.call_id
            ],
        )
        for item in state.tool_calls
    ]

    approvals: list[TimelineApproval] = []
    for request in approval_requests:
        approvals.append(
            TimelineApproval(
                request_id=request.request_id,
                action=request.action.value,
                risk_tier=request.risk_tier.value,
                decision={
                    "decision": request.status,
                    "reason": request.decision_note or "approval store record",
                    "policy_snapshot_id": request.policy_snapshot_id,
                },
                status=request.status,
                decision_actor=request.decision_actor,
            )
        )

    validation = state.validation
    validation_block = TimelineValidation(
        ran=validation is not None,
        summary=validation.summary if validation else "no validation recorded",
    )

    proposals = [
        {"kind": proposal.kind, "ref": proposal.ref} for proposal in state.proposals
    ]

    started_at = state.costs.started_at or state.created_at
    ended_at = state.costs.ended_at or state.updated_at
    duration_ms = _duration_ms(started_at, ended_at) if ended_at else 0

    redaction_complete = all(
        all(
            not isinstance(value, str) or len(value.encode("utf-8")) <= 2048
            for value in event.payload.values()
        )
        for event in trace_events
    )

    return RunTimeline(
        run_id=state.run_id,
        tenant_id=state.tenant_id,
        task_type=state.task_type.value,
        status=state.status.value,
        actor=TimelineActor(
            actor_id=state.actor_id,
            roles=[role.value for role in state.subject.roles],
        ),
        policy_snapshot_id=state.policy_snapshot_id,
        summary=state.report.markdown.splitlines()[0] if state.report else f"{state.task_type.value} run",
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        nodes=nodes,
        citations=citations,
        tool_calls=tool_calls,
        approvals=approvals,
        validation=validation_block,
        proposals=proposals,
        costs={
            "by_node": {
                name: cost.model_dump(mode="json") for name, cost in state.costs.by_node.items()
            },
            "total": state.costs.total.model_dump(mode="json"),
        },
        safety_invariants=TimelineSafetyInvariants(redaction_complete=redaction_complete),
        failures=[
            {
                "failure_id": item.failure_id,
                "category": item.category,
                "node_name": item.node_name,
                "message": _redact_excerpt(item.message)[0],
            }
            for item in state.failures
        ],
    )


def serialize_timeline(timeline: RunTimeline) -> str:
    payload = json.loads(timeline.model_dump_json())
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def write_timeline(sac_root: Path, run_id: str) -> Path:
    timeline = build_timeline(sac_root, run_id)
    path = timeline_path(sac_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = serialize_timeline(timeline)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    return path


def timeline_content_hash(timeline: RunTimeline) -> str:
    return hashlib.sha256(serialize_timeline(timeline).encode("utf-8")).hexdigest()
