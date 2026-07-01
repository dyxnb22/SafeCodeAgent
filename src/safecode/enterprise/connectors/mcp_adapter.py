"""MCP adapter that registers allowlisted tools only.

中文模块说明：Enterprise 侧 MCP 适配层，仅注册本地 allowlist 已分类的工具。
- 架构位置：Integration 平面；忽略 MCP server 自报的 metadata（决策 D10）。
- 安全不变量：未在 allowlist 的工具不会注册；默认 tier 为 BLOCK。
- 学习路径：读 ``mcp_allowlist.py`` 与 ``test_mcp_server_classification_ignored.py``。
"""

from __future__ import annotations

import logging
from pathlib import Path

from safecode.context.redactor import redact_secrets
from safecode.enterprise.approvals.store import Action
from safecode.enterprise.connectors.mcp_allowlist import DEFAULT_BLOCK_TIER, MCPAllowlist, lookup_allowlist
from safecode.enterprise.tools.registry import ToolRegistry, ToolSpec
from safecode.mcp.discovery import MCPDiscovery, MCPTool

logger = logging.getLogger(__name__)

MAX_OUTPUT_CHARS = 4096


def _tool_key(server: str, tool: str) -> str:
    return f"mcp:{server}:{tool}"


def redact_and_bound_output(text: str) -> str:
    redacted = redact_secrets(text)
    if len(redacted) > MAX_OUTPUT_CHARS:
        return redacted[: MAX_OUTPUT_CHARS - 3] + "..."
    return redacted


def register_allowlisted_mcp_tools(
    project_root: Path,
    registry: ToolRegistry,
    allowlist: MCPAllowlist,
) -> list[str]:
    discovery = MCPDiscovery(project_root)
    registered: list[str] = []
    for item in discovery.list_tools():
        entry = lookup_allowlist(allowlist, item.server, item.name.split(".")[-1])
        if entry is None:
            continue
        if item.risk:
            logger.info("ignored MCP server-claimed category %s for %s:%s", item.risk, item.server, item.name)
        key = _tool_key(item.server, item.name.split(".")[-1])
        action = Action.mcp_read if entry.category.value.endswith("read") or "read" in entry.category.value else Action.mcp_write
        registry.register(
            ToolSpec(
                name=key,
                description=f"MCP tool {item.server}/{item.name}",
                category=entry.category,
                approval_tier=entry.approval_tier,
                action=action,
                requires_network=entry.category.value.endswith("network"),
                requires_write="write" in entry.category.value,
                capabilities=["mcp"],
                audit_event="tool.proposed",
            )
        )
        registered.append(key)
    return registered


def classify_discovered_tool(item: MCPTool, allowlist: MCPAllowlist):
    entry = lookup_allowlist(allowlist, item.server, item.name.split(".")[-1])
    if entry is None:
        return DEFAULT_BLOCK_TIER
    return entry.approval_tier
