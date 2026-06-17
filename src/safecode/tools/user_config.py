"""User-declared project tool metadata from .sac/tools.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

from safecode.tools.registry import AuditEventRef, PermissionCategory, ToolArgSchema, ToolRiskLevel, ToolSpec


def load_user_tool_specs(project_root: Path) -> tuple[list[ToolSpec], list[str]]:
    """Load user-declared tools fail-soft.

    Expected shape:

    [[tools]]
    name = "db.dump"
    description = "Dump local DB schema"
    command = "python scripts/dump_schema.py"
    risk = "low"
    permission = "read"
    approval = false
    experimental = true
    """
    path = project_root / ".sac" / "tools.toml"
    if not path.exists():
        return [], []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [], [f"{path}: {type(exc).__name__}"]

    raw_tools = data.get("tools", [])
    if not isinstance(raw_tools, list):
        return [], ["tools must be an array of tables"]

    specs: list[ToolSpec] = []
    errors: list[str] = []
    for index, item in enumerate(raw_tools, start=1):
        if not isinstance(item, dict):
            errors.append(f"tools[{index}] must be a table")
            continue
        try:
            name = str(item["name"])
            permission = PermissionCategory(str(item.get("permission", "shell")))
            risk = ToolRiskLevel(str(item.get("risk", "medium")))
            approval = bool(item.get("approval", risk != ToolRiskLevel.LOW))
            command = str(item.get("command", ""))
            args = []
            if command:
                args.append(ToolArgSchema(name="command", type="str", required=False, description=command))
            specs.append(
                ToolSpec(
                    name=name,
                    version=str(item.get("version", "1.0.0")),
                    description=str(item.get("description", "")) or f"User-declared tool {name}",
                    risk=risk,
                    permission_category=permission,
                    requires_human_approval=approval,
                    args=args,
                    audit_event=AuditEventRef(event_type="user_tool_declared", description="Loaded from .sac/tools.toml"),
                )
            )
        except Exception as exc:
            errors.append(f"tools[{index}] invalid: {type(exc).__name__}")
    return specs, errors
