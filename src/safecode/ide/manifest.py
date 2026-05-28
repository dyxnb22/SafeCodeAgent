"""Generate a lightweight IDE integration manifest."""

import json
from pathlib import Path


def render_manifest() -> str:
    """Return a JSON manifest describing SafeCode commands for IDE adapters."""
    data = {
        "name": "SafeCode Agent",
        "commands": [
            {"id": "safecode.ask", "command": "sac ask"},
            {"id": "safecode.edit", "command": "sac edit"},
            {"id": "safecode.apply", "command": "sac apply"},
            {"id": "safecode.rollback", "command": "sac rollback --last"},
            {"id": "safecode.history", "command": "sac history"},
        ],
    }
    return json.dumps(data, indent=2)


def write_manifest(project_root: Path) -> Path:
    """Write the IDE manifest under .sac."""
    path = project_root / ".sac" / "ide-manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_manifest(), encoding="utf-8")
    return path
