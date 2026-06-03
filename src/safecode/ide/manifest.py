"""Generate a lightweight IDE integration manifest."""

import json
from pathlib import Path

_JSONRPC_CONTRACT_VERSION = "1"


def render_manifest() -> str:
    """Return a JSON manifest describing SafeCode commands for IDE adapters."""
    data = {
        "name": "SafeCode Agent",
        "jsonrpc_transport": {
            "launch_command": ["sac", "api", "jsonrpc"],
            "protocol": "json-rpc-2.0",
            "transport": "stdio",
            "contract_version": _JSONRPC_CONTRACT_VERSION,
            "supported_methods": ["ask", "report", "edit", "apply"],
            "note": "EXPERIMENTAL: not a stable contract",
        },
        "pending_diff_targets": {
            "open_diff_command": "sac ide open-diff",
            "note": "Opens the pending unified diff for editor preview",
        },
        "commands": [
            {"id": "safecode.ask", "command": "sac ask"},
            {"id": "safecode.edit", "command": "sac edit"},
            {"id": "safecode.apply", "command": "sac apply"},
            {"id": "safecode.rollback", "command": "sac rollback --last"},
            {"id": "safecode.history", "command": "sac history"},
            {"id": "safecode.openDiff", "command": "sac ide open-diff"},
            {"id": "safecode.openSelectedFiles", "command": "sac ide open-files"},
            {"id": "safecode.apiJsonrpc", "command": "sac api jsonrpc"},
        ],
    }
    return json.dumps(data, indent=2)


def write_manifest(project_root: Path) -> Path:
    """Write the IDE manifest under .sac."""
    path = project_root / ".sac" / "ide-manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_manifest(), encoding="utf-8")
    return path
