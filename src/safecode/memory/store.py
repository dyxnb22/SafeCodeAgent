"""Store low-risk project facts."""

import json
from pathlib import Path


class MemoryStore:
    """Persist simple non-secret project facts in .sac/memory.json."""

    def __init__(self, project_root: Path) -> None:
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
        data = self.read()
        data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _looks_sensitive(self, key: str, value: str) -> bool:
        lowered = f"{key} {value}".lower()
        return any(word in lowered for word in ["token", "secret", "password", "api_key", "private_key"])
