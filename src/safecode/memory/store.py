"""Store low-risk project facts."""

import json
from pathlib import Path

from safecode.memory.facade import MemoryFacade


class MemoryStore:
    """Compatibility wrapper for legacy low-risk project facts."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.path = project_root / ".sac" / "memory.json"

    def read(self) -> dict[str, str]:
        """Read memory facts."""
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def remember(self, key: str, value: str) -> None:
        """Store one low-risk fact."""
        if self._looks_sensitive(key, value):
            raise ValueError("Refusing to store a value that looks sensitive.")
        MemoryFacade(self.project_root).add_note(f"- {key}: {value}")

    def _looks_sensitive(self, key: str, value: str) -> bool:
        lowered = f"{key} {value}".lower()
        return any(word in lowered for word in ["token", "secret", "password", "api_key", "private_key"])
