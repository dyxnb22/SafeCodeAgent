"""Native tool enterprise spec wrappers (v1.3.1-T2)."""

from __future__ import annotations

from safecode.enterprise.approvals.store import Action
from safecode.enterprise.tools.registry import (
    ApprovalTier,
    ToolCategory,
    ToolRegistry,
    ToolSpec,
)

NATIVE_TOOL_NAMES: tuple[str, ...] = (
    "read_file",
    "search",
    "command",
    "github_read",
    "github_write",
    "web_fetch",
)

_NATIVE_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="read_file",
        description="Read a bounded file inside the project root.",
        category=ToolCategory.read_local,
        approval_tier=ApprovalTier.AUTO,
        action=Action.retrieval_source_access,
        capabilities=["read"],
        audit_event="tool.executed",
    ),
    ToolSpec(
        name="search",
        description="Search project files with a literal pattern.",
        category=ToolCategory.read_local,
        approval_tier=ApprovalTier.AUTO,
        action=Action.retrieval_source_access,
        capabilities=["search"],
        audit_event="tool.executed",
    ),
    ToolSpec(
        name="command",
        description="Propose and execute a local command through the sandbox gate.",
        category=ToolCategory.command,
        approval_tier=ApprovalTier.CONFIRM,
        action=Action.command_execute,
        capabilities=["execute"],
        audit_event="tool.proposed",
    ),
    ToolSpec(
        name="github_read",
        description="Read GitHub issues, pull requests, or files via gh CLI.",
        category=ToolCategory.read_network,
        approval_tier=ApprovalTier.AUTO,
        action=Action.github_read,
        requires_network=True,
        capabilities=["read"],
        audit_event="tool.executed",
    ),
    ToolSpec(
        name="github_write",
        description="Write GitHub comments, branches, or pull requests.",
        category=ToolCategory.write_network,
        approval_tier=ApprovalTier.GATE,
        action=Action.github_write_comment,
        requires_network=True,
        requires_write=True,
        capabilities=["write"],
        audit_event="tool.proposed",
    ),
    ToolSpec(
        name="web_fetch",
        description="Fetch remote text content over HTTP with network policy gates.",
        category=ToolCategory.read_network,
        approval_tier=ApprovalTier.CONFIRM,
        action=Action.mcp_read,
        requires_network=True,
        capabilities=["read"],
        audit_event="tool.proposed",
    ),
)


def native_tool_specs() -> tuple[ToolSpec, ...]:
    return _NATIVE_SPECS


def register_native_tools(registry: ToolRegistry | None = None) -> ToolRegistry:
    target = registry or ToolRegistry()
    for spec in _NATIVE_SPECS:
        target.register(spec)
    return target
