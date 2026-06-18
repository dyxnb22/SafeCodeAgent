"""MCP allowlist schema and loader."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from safecode.enterprise.tools.registry import ApprovalTier, ToolCategory

DEFAULT_BLOCK_TIER = ApprovalTier.BLOCK


class MCPAllowlistEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ToolCategory
    approval_tier: ApprovalTier
    server_claimed_category: str | None = None


class MCPAllowlist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    tools: dict[str, MCPAllowlistEntry] = Field(default_factory=dict)


class MCPAllowlistError(Exception):
    """Allowlist validation error."""


def load_allowlist(path: Path) -> MCPAllowlist:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise MCPAllowlistError("allowlist root must be a mapping")
    tools_raw = payload.get("tools") or {}
    tools: dict[str, MCPAllowlistEntry] = {}
    for key, value in tools_raw.items():
        if not isinstance(value, dict):
            raise MCPAllowlistError(f"invalid allowlist entry for {key}")
        tools[str(key)] = MCPAllowlistEntry.model_validate(value)
    return MCPAllowlist(version=int(payload.get("version", 1)), tools=tools)


def lookup_allowlist(allowlist: MCPAllowlist, server_id: str, tool: str) -> MCPAllowlistEntry | None:
    return allowlist.tools.get(f"{server_id}:{tool}")
