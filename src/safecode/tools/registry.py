"""Internal tool schema registry for SafeCode Agent (v2.2.0)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolRiskLevel(StrEnum):
    """Risk classification for a registered tool."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PermissionCategory(StrEnum):
    """Broad permission bucket that a tool falls under."""

    READ = "read"
    WRITE = "write"
    SHELL = "shell"
    SANDBOX = "sandbox"
    MCP = "mcp"
    SUBAGENT = "subagent"
    AUDIT = "audit"


class ToolArgSchema(BaseModel):
    """Schema for a single tool argument."""

    model_config = ConfigDict(frozen=True)

    name: str
    type: Literal["str", "int", "bool", "path", "dict", "list"]
    required: bool = True
    description: str = ""


class AuditEventRef(BaseModel):
    """Reference to the audit event type emitted by a tool."""

    model_config = ConfigDict(frozen=True)

    event_type: str
    description: str = ""


class ToolSpec(BaseModel):
    """Full schema for a SafeCode internal tool."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    risk: ToolRiskLevel
    permission_category: PermissionCategory
    requires_human_approval: bool
    args: list[ToolArgSchema] = Field(default_factory=list)
    audit_event: AuditEventRef | None = None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: list[ToolSpec] = [
    ToolSpec(
        name="context.collect",
        description="Collect bounded, redacted project context for a task query.",
        risk=ToolRiskLevel.LOW,
        permission_category=PermissionCategory.READ,
        requires_human_approval=False,
        args=[
            ToolArgSchema(name="query", type="str", required=True, description="Task or question to collect context for."),
            ToolArgSchema(name="limit", type="int", required=False, description="Maximum number of context sources to include."),
        ],
        audit_event=AuditEventRef(event_type="context_collected", description="Emitted when context is packed for an agent step."),
    ),
    ToolSpec(
        name="context.read",
        description="Read and index a specific project file within the budget boundary.",
        risk=ToolRiskLevel.LOW,
        permission_category=PermissionCategory.READ,
        requires_human_approval=False,
        args=[
            ToolArgSchema(name="target", type="path", required=True, description="Relative path to the file to read."),
        ],
        audit_event=AuditEventRef(event_type="file_read", description="Emitted when a file is read into the agent context."),
    ),
    ToolSpec(
        name="patch.propose",
        description="Create a pending patch proposal after diff preview. Does not write files.",
        risk=ToolRiskLevel.MEDIUM,
        permission_category=PermissionCategory.WRITE,
        requires_human_approval=True,
        args=[
            ToolArgSchema(name="target", type="path", required=True, description="Path to the file to patch."),
            ToolArgSchema(name="patch_text", type="str", required=True, description="Unified diff patch text."),
        ],
        audit_event=AuditEventRef(event_type="patch_proposed", description="Emitted when a patch proposal is created for review."),
    ),
    ToolSpec(
        name="patch.apply",
        description="Apply a reviewed and approved patch through checkpoint and audit.",
        risk=ToolRiskLevel.MEDIUM,
        permission_category=PermissionCategory.WRITE,
        requires_human_approval=True,
        args=[
            ToolArgSchema(name="patch_id", type="str", required=True, description="ID of the approved pending patch."),
        ],
        audit_event=AuditEventRef(event_type="patch_applied", description="Emitted when a patch is applied to the project files."),
    ),
    ToolSpec(
        name="shell.propose",
        description="Propose a policy-classified shell command for user review before execution.",
        risk=ToolRiskLevel.MEDIUM,
        permission_category=PermissionCategory.SHELL,
        requires_human_approval=True,
        args=[
            ToolArgSchema(name="command", type="str", required=True, description="Shell command to propose."),
        ],
        audit_event=AuditEventRef(event_type="command_proposed", description="Emitted when a shell command is proposed for approval."),
    ),
    ToolSpec(
        name="shell.run",
        description="Run an approved, policy-classified shell command via argv execution.",
        risk=ToolRiskLevel.MEDIUM,
        permission_category=PermissionCategory.SHELL,
        requires_human_approval=True,
        args=[
            ToolArgSchema(name="command", type="str", required=True, description="Approved shell command to run."),
            ToolArgSchema(name="approved", type="bool", required=False, description="Whether the user has approved the command."),
        ],
        audit_event=AuditEventRef(event_type="command_run", description="Emitted after a shell command completes."),
    ),
    ToolSpec(
        name="checkpoint.rollback",
        description="Restore project files from the latest checkpoint.",
        risk=ToolRiskLevel.MEDIUM,
        permission_category=PermissionCategory.WRITE,
        requires_human_approval=True,
        args=[
            ToolArgSchema(name="checkpoint_id", type="str", required=False, description="Checkpoint ID to restore; defaults to the latest."),
        ],
        audit_event=AuditEventRef(event_type="rollback", description="Emitted when a checkpoint rollback is applied."),
    ),
    ToolSpec(
        name="sandbox.plan",
        description="Generate a dry-run sandbox execution plan without running the command.",
        risk=ToolRiskLevel.LOW,
        permission_category=PermissionCategory.SANDBOX,
        requires_human_approval=False,
        args=[
            ToolArgSchema(name="command", type="str", required=True, description="Command to generate a sandbox plan for."),
        ],
        audit_event=AuditEventRef(event_type="sandbox_plan", description="Emitted when a sandbox execution plan is generated."),
    ),
    ToolSpec(
        name="sandbox.propose",
        description="Create a pending sandbox execution proposal for user approval and preflight.",
        risk=ToolRiskLevel.MEDIUM,
        permission_category=PermissionCategory.SANDBOX,
        requires_human_approval=True,
        args=[
            ToolArgSchema(name="command", type="str", required=True, description="Command to propose for sandbox execution."),
            ToolArgSchema(name="backend", type="str", required=False, description="Sandbox backend (noop, macos, linux, docker)."),
        ],
        audit_event=AuditEventRef(event_type="sandbox_proposed", description="Emitted when a sandbox execution proposal is created."),
    ),
    ToolSpec(
        name="sandbox.execute",
        description="Execute an approved and preflighted sandbox proposal through the Noop adapter.",
        risk=ToolRiskLevel.HIGH,
        permission_category=PermissionCategory.SANDBOX,
        requires_human_approval=True,
        args=[
            ToolArgSchema(name="proposal_id", type="str", required=True, description="ID of the approved sandbox proposal."),
        ],
        audit_event=AuditEventRef(event_type="sandbox_executed", description="Emitted when a sandbox command completes execution."),
    ),
    ToolSpec(
        name="mcp.call_readonly",
        description="Call an MCP read-only tool with full audit logging and output size limits.",
        risk=ToolRiskLevel.LOW,
        permission_category=PermissionCategory.MCP,
        requires_human_approval=False,
        args=[
            ToolArgSchema(name="tool_name", type="str", required=True, description="Fully qualified MCP tool name."),
            ToolArgSchema(name="input_json", type="dict", required=False, description="JSON input for the MCP tool."),
        ],
        audit_event=AuditEventRef(event_type="mcp_call_readonly", description="Emitted when a read-only MCP tool call completes."),
    ),
    ToolSpec(
        name="mcp.propose_write",
        description="Create an MCP write proposal for user review; does not execute the write.",
        risk=ToolRiskLevel.MEDIUM,
        permission_category=PermissionCategory.MCP,
        requires_human_approval=True,
        args=[
            ToolArgSchema(name="tool_name", type="str", required=True, description="Fully qualified MCP tool name."),
            ToolArgSchema(name="input_json", type="dict", required=False, description="JSON input for the MCP write operation."),
        ],
        audit_event=AuditEventRef(event_type="mcp_write_proposed", description="Emitted when an MCP write proposal is created."),
    ),
    ToolSpec(
        name="subagent.dispatch",
        description="Dispatch a bounded, read-only investigation subagent and merge findings into the main loop.",
        risk=ToolRiskLevel.LOW,
        permission_category=PermissionCategory.SUBAGENT,
        requires_human_approval=False,
        args=[
            ToolArgSchema(name="task", type="str", required=True, description="Investigation task description."),
            ToolArgSchema(name="scope", type="str", required=True, description="File paths or patterns to investigate."),
            ToolArgSchema(name="max_steps", type="int", required=True, description="Maximum investigation steps (1-10)."),
        ],
        audit_event=AuditEventRef(event_type="subagent_dispatched", description="Emitted when a subagent investigation is dispatched."),
    ),
    ToolSpec(
        name="subagent.run_readonly",
        description="Run a bounded, read-only subagent task and write results to .sac/subagents/.",
        risk=ToolRiskLevel.LOW,
        permission_category=PermissionCategory.SUBAGENT,
        requires_human_approval=False,
        args=[
            ToolArgSchema(name="task_id", type="str", required=True, description="Unique identifier for the subagent task."),
            ToolArgSchema(name="goal", type="str", required=True, description="Goal or question for the subagent."),
        ],
        audit_event=AuditEventRef(event_type="subagent_run", description="Emitted when a readonly subagent task completes."),
    ),
    ToolSpec(
        name="subagent.inspect",
        description="Inspect and summarize completed subagent task results without side effects.",
        risk=ToolRiskLevel.LOW,
        permission_category=PermissionCategory.SUBAGENT,
        requires_human_approval=False,
        args=[
            ToolArgSchema(name="task_id", type="str", required=True, description="ID of the subagent task to inspect."),
        ],
        audit_event=AuditEventRef(event_type="subagent_inspect", description="Emitted when subagent task results are inspected."),
    ),
    ToolSpec(
        name="report.render",
        description="Render a read-only session summary or audit report.",
        risk=ToolRiskLevel.LOW,
        permission_category=PermissionCategory.AUDIT,
        requires_human_approval=False,
        args=[
            ToolArgSchema(name="session_id", type="str", required=False, description="Session ID to render; defaults to the current session."),
        ],
        audit_event=AuditEventRef(event_type="report_rendered", description="Emitted when a session report is rendered."),
    ),
    ToolSpec(
        name="audit.verify",
        description="Verify the integrity of the audit log hash-chain and anchor file.",
        risk=ToolRiskLevel.LOW,
        permission_category=PermissionCategory.AUDIT,
        requires_human_approval=False,
        args=[],
        audit_event=AuditEventRef(event_type="audit_verified", description="Emitted when the audit log integrity check completes."),
    ),
]

# Index by name for O(1) lookup — built once at module load.
_REGISTRY_INDEX: dict[str, ToolSpec] = {spec.name: spec for spec in _REGISTRY}


class ToolRegistry:
    """Read-only registry of SafeCode internal tool schemas.

    The registry is deterministic and keyless: it is constructed from a fixed
    list at module load time. No external state is read or written.
    """

    def list(self) -> list[ToolSpec]:
        """Return all registered tools sorted by name."""
        return sorted(_REGISTRY, key=lambda s: s.name)

    def get(self, name: str) -> ToolSpec:
        """Return the ToolSpec for *name*, or raise KeyError if unknown."""
        if name not in _REGISTRY_INDEX:
            raise KeyError(f"Unknown tool: {name!r}")
        return _REGISTRY_INDEX[name]

    def names(self) -> list[str]:
        """Return all registered tool names sorted alphabetically."""
        return sorted(_REGISTRY_INDEX)

    def by_permission(self, category: PermissionCategory) -> list[ToolSpec]:
        """Return tools whose permission_category matches *category*."""
        return sorted(
            (s for s in _REGISTRY if s.permission_category == category),
            key=lambda s: s.name,
        )

    def by_risk(self, level: ToolRiskLevel) -> list[ToolSpec]:
        """Return tools whose risk matches *level*."""
        return sorted(
            (s for s in _REGISTRY if s.risk == level),
            key=lambda s: s.name,
        )

    def requiring_approval(self) -> list[ToolSpec]:
        """Return tools that require human approval."""
        return sorted(
            (s for s in _REGISTRY if s.requires_human_approval),
            key=lambda s: s.name,
        )
