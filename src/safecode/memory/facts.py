"""Project convention facts store (v6.2.1).

Facts are proposed automatically by the agent or manually by the user.
They require explicit user approval before being injected into the agent context.
Project-local files cannot write or approve facts — only the CLI gate can.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safecode.context.redactor import redact_secrets

_STORE_VERSION = 1
_MAX_FACTS = 200
_MAX_VALUE_LEN = 300

_KNOWN_KEYS = frozenset(
    {"test_command", "lint_command", "typecheck_command", "build_command",
     "guarded_dir", "api_constraint", "convention", "project_note"}
)

_SENSITIVE_WORDS = frozenset({"token", "secret", "password", "api_key", "apikey", "private_key"})


@dataclass
class ProjectFact:
    """One discrete project convention or constraint."""

    fact_id: str
    key: str
    value: str
    source: str       # "auto" | "user"
    status: str       # "pending" | "approved" | "rejected"
    created_at: str
    approved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectFact":
        return cls(
            fact_id=str(data.get("fact_id", "")),
            key=str(data.get("key", "convention")),
            value=str(data.get("value", "")),
            source=str(data.get("source", "auto")),
            status=str(data.get("status", "pending")),
            created_at=str(data.get("created_at", "")),
            approved_at=data.get("approved_at"),
        )

    def summary_line(self) -> str:
        return f"[{self.fact_id[:8]}] {self.key}: {self.value[:80]}"


def _make_fact_id(key: str, value: str) -> str:
    return hashlib.sha256(f"{key}:{value}".encode()).hexdigest()[:16]


class ProjectFactStore:
    """JSON store for pending and approved project convention facts."""

    def __init__(self, sac_dir: Path) -> None:
        self.path = sac_dir / "memory" / "facts.json"

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_facts(self, status: str | None = None) -> list[ProjectFact]:
        """Return facts filtered by status, or all facts if status is None."""
        data = self._load()
        facts = [ProjectFact.from_dict(f) for f in data.get("facts", [])]
        if status is not None:
            facts = [f for f in facts if f.status == status]
        return facts

    def get(self, fact_id: str) -> ProjectFact | None:
        for fact in self.list_facts():
            if fact.fact_id == fact_id or fact.fact_id.startswith(fact_id):
                return fact
        return None

    def approved_context(self, max_chars: int = 1000) -> str:
        """Format approved facts as a compact context block."""
        approved = self.list_facts(status="approved")
        if not approved:
            return ""
        lines = ["## Approved Project Conventions"]
        chars = len(lines[0])
        for f in approved:
            line = f"- {f.key}: {f.value}"
            if chars + len(line) + 2 > max_chars:
                break
            lines.append(line)
            chars += len(line) + 2
        return "\n".join(lines) if len(lines) > 1 else ""

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def propose(self, key: str, value: str, source: str = "auto") -> ProjectFact | None:
        """Propose a new fact. Returns None if duplicate or value looks sensitive."""
        value = redact_secrets(value[:_MAX_VALUE_LEN])
        if _looks_sensitive(value) or _looks_sensitive(key):
            return None
        fact_id = _make_fact_id(key, value)
        existing = self.get(fact_id)
        if existing is not None:
            return None  # already exists
        fact = ProjectFact(
            fact_id=fact_id,
            key=key,
            value=value,
            source=source,
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._append(fact)
        return fact

    def approve(self, fact_id: str) -> ProjectFact:
        """Approve a pending fact. Raises ValueError if not found or not pending."""
        data = self._load()
        facts = data.get("facts", [])
        matched = None
        for i, f in enumerate(facts):
            fid = str(f.get("fact_id", ""))
            if fid == fact_id or fid.startswith(fact_id):
                matched = i
                break
        if matched is None:
            raise ValueError(f"Fact '{fact_id}' not found.")
        fact_dict = facts[matched]
        if fact_dict.get("status") != "pending":
            raise ValueError(f"Fact '{fact_id}' is not pending (status={fact_dict.get('status')}).")
        fact_dict["status"] = "approved"
        fact_dict["approved_at"] = datetime.now(timezone.utc).isoformat()
        facts[matched] = fact_dict
        data["facts"] = facts
        self._save(data)
        return ProjectFact.from_dict(fact_dict)

    def reject(self, fact_id: str) -> ProjectFact:
        """Reject a pending fact."""
        data = self._load()
        facts = data.get("facts", [])
        matched = None
        for i, f in enumerate(facts):
            fid = str(f.get("fact_id", ""))
            if fid == fact_id or fid.startswith(fact_id):
                matched = i
                break
        if matched is None:
            raise ValueError(f"Fact '{fact_id}' not found.")
        facts[matched]["status"] = "rejected"
        data["facts"] = facts
        self._save(data)
        return ProjectFact.from_dict(facts[matched])

    # ------------------------------------------------------------------
    # Auto-detection helpers
    # ------------------------------------------------------------------

    def propose_from_session_summary(self, commands_run: list[str], touched_files: list[str]) -> list[ProjectFact]:
        """Propose conventions inferred from a session summary."""
        proposed: list[ProjectFact] = []
        for cmd in commands_run:
            key = _classify_command(cmd)
            if key:
                fact = self.propose(key, cmd, source="auto")
                if fact:
                    proposed.append(fact)
        guarded = _detect_guarded_dirs(touched_files)
        for d in guarded:
            fact = self.propose("guarded_dir", d, source="auto")
            if fact:
                proposed.append(fact)
        return proposed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": _STORE_VERSION, "facts": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"version": _STORE_VERSION, "facts": []}
            if not isinstance(data.get("facts"), list):
                data["facts"] = []
            return data
        except (json.JSONDecodeError, OSError):
            return {"version": _STORE_VERSION, "facts": []}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _append(self, fact: ProjectFact) -> None:
        data = self._load()
        facts = data.get("facts", [])
        facts.append(fact.to_dict())
        facts = facts[-_MAX_FACTS:]
        data["facts"] = facts
        self._save(data)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_TEST_CMDS = re.compile(r"\b(pytest|python.*-m.*pytest|npm.*test|go test|cargo test|jest|vitest)\b", re.IGNORECASE)
_LINT_CMDS = re.compile(r"\b(ruff|flake8|pylint|eslint|golangci-lint|cargo clippy)\b", re.IGNORECASE)
_TYPECHECK_CMDS = re.compile(r"\b(mypy|pyright|tsc|typescript)\b", re.IGNORECASE)
_BUILD_CMDS = re.compile(r"\b(npm run build|cargo build|go build|python.*-m.*build|uv build)\b", re.IGNORECASE)

_GENERATED_DIRS = re.compile(r"(generated|__pycache__|\.mypy_cache|node_modules|dist|build)", re.IGNORECASE)


def _classify_command(cmd: str) -> str | None:
    if _TEST_CMDS.search(cmd):
        return "test_command"
    if _LINT_CMDS.search(cmd):
        return "lint_command"
    if _TYPECHECK_CMDS.search(cmd):
        return "typecheck_command"
    if _BUILD_CMDS.search(cmd):
        return "build_command"
    return None


def _detect_guarded_dirs(files: list[str]) -> list[str]:
    dirs: set[str] = set()
    for f in files:
        parts = Path(f).parts
        for part in parts[:-1]:
            if _GENERATED_DIRS.search(part):
                dirs.add(part)
    return sorted(dirs)


def _looks_sensitive(text: str) -> bool:
    lowered = text.lower()
    return any(w in lowered for w in _SENSITIVE_WORDS)
