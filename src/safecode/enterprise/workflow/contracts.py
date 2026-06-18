"""Node patch contracts and trace event drafts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

NodeStatus = Literal["ok", "soft_failure", "fatal"]
NodeOutputStatus = Literal["ok", "soft_failure", "fatal", "skipped"]
NodeArtifactKind = Literal["citation_set", "plan", "proposal", "validation", "report", "evidence"]


class NodeCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    provider: str = "mock"
    request_count: int = 0


class RunCosts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by_node: dict[str, NodeCost] = Field(default_factory=dict)
    total: NodeCost = Field(default_factory=NodeCost)
    dollars_estimate: float | None = None
    started_at: str = ""
    ended_at: str | None = None


class TraceEventDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    kind: str
    payload: dict[str, str] = Field(default_factory=dict)


class NodeArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: NodeArtifactKind
    ref: str


class NodeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_name: str
    status: NodeOutputStatus
    summary: str
    artifacts: list[NodeArtifact] = Field(default_factory=list)
    started_at: str
    ended_at: str


class NodePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_name: str
    status: NodeStatus
    state_updates: dict[str, Any] = Field(default_factory=dict)
    events: list[TraceEventDraft] = Field(default_factory=list)
    cost: NodeCost = Field(default_factory=NodeCost)
    duration_ms: int = 0
