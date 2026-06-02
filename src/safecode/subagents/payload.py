"""Versioned subagent dispatch journal payload model (v2.9.6).

Provides typed, tolerant loading for subagent_dispatch journal event payloads.
Old journals (pre-v2.9.6, without ``payload_version``) parse with the default
version (1) and remain fully compatible. Invalid payloads are skipped with a
``RuntimeWarning`` rather than crashing.

Status: evolving. The payload format is versioned to support forward-compatible
loading as the subagent system matures toward v3.0 contract stabilization.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Payload versions supported by this runtime.
SUPPORTED_PAYLOAD_VERSIONS: frozenset[int] = frozenset({1})

# Current version written to new journal events.
CURRENT_PAYLOAD_VERSION: int = 1


class SubagentDispatchPayload(BaseModel):
    """Typed model for the ``subagent_dispatch`` key in journal event payloads.

    All fields have safe defaults so that old journal events (pre-v2.9.6,
    which lack ``payload_version``) parse without errors.

    Fields
    ------
    payload_version:
        Schema version for this payload. Old journals default to 1.
    task_id:
        Unique ID for the dispatched subagent task.
    summary:
        Human-readable summary of the investigation.
    observations:
        List of structured observations from the subagent.
    files_inspected:
        File paths examined by the subagent.
    errors:
        Error messages from failed or blocked tasks.
    blocked:
        Whether the subagent was blocked by policy or approval gates.
    success:
        Whether the subagent completed successfully.
    """

    payload_version: int = Field(default=CURRENT_PAYLOAD_VERSION)
    task_id: str = ""
    summary: str = ""
    observations: list[str] = Field(default_factory=list)
    files_inspected: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    blocked: bool = False
    success: bool = False

    model_config = {"extra": "ignore"}
