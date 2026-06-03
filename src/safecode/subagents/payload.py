"""Versioned subagent dispatch journal payload model (v2.9.6 / v3.4.3).

Provides typed, tolerant loading for subagent_dispatch journal event payloads.
Old journals (pre-v2.9.6, without ``payload_version``) parse with the default
version (1) and remain fully compatible. v1 journals still load tolerantly.
v2 payloads add synthesis and cancellation fields with safe defaults.
Invalid payloads are skipped with a ``RuntimeWarning`` rather than crashing.
Unsupported future versions warn and fail closed.

Status: v2 promoted to supported at v3.4.3. v1 remains supported for
backward compatibility.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Payload versions supported by this runtime.
SUPPORTED_PAYLOAD_VERSIONS: frozenset[int] = frozenset({1, 2})

# Current version written to new journal events.
CURRENT_PAYLOAD_VERSION: int = 2


class SubagentDispatchPayload(BaseModel):
    """Typed model for the ``subagent_dispatch`` key in journal event payloads.

    All fields have safe defaults so that old journal events (pre-v2.9.6,
    which lack ``payload_version``) parse without errors. v1 payloads load
    tolerantly; v2 fields default to empty/False when absent.

    Fields (v1)
    -----------
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

    Fields (v2, T-3.4.3-A)
    -----------------------
    synthesis_summary:
        Synthesised parent-side narrative across merged findings.
    synthesis_key_findings:
        Key observations extracted by the parent synthesis step.
    synthesis_risks:
        Risks identified by the parent synthesis step.
    synthesis_source_task_ids:
        Task IDs of successful findings used in synthesis.
    cancelled_task_ids:
        Task IDs that were cancelled before completion.
    """

    # Default 1 for backward compat: old journals without payload_version parse as v1.
    # New journals use CURRENT_PAYLOAD_VERSION (2) written by record_subagent_dispatch.
    payload_version: int = Field(default=1)
    task_id: str = ""
    summary: str = ""
    observations: list[str] = Field(default_factory=list)
    files_inspected: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    blocked: bool = False
    success: bool = False

    # v2 fields — safe defaults so v1 payloads load without errors.
    synthesis_summary: str = ""
    synthesis_key_findings: list[str] = Field(default_factory=list)
    synthesis_risks: list[str] = Field(default_factory=list)
    synthesis_source_task_ids: list[str] = Field(default_factory=list)
    cancelled_task_ids: list[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}
