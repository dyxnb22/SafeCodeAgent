"""Typed, explainable read pipeline for project memory context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ContextLedgerItem:
    source: str
    content: str
    injected: bool
    reason: str
    count: int


class ContextLedger:
    """Collect trusted context and explain every included or withheld source."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.sac_dir = self.project_root / ".sac"

    def collect(self) -> list[ContextLedgerItem]:
        from safecode.memory.facade import MemoryFacade
        from safecode.memory.facts import ProjectFactStore
        from safecode.memory.session_store import SessionSummaryStore
        from safecode.memory.summary import format_memory_context
        from safecode.memory.workspace_memory import WorkspaceMemoryStore

        fact_store = ProjectFactStore(self.sac_dir)
        approved = fact_store.list_facts(status="approved")
        pending = fact_store.list_facts(status="pending")
        facts_content = fact_store.approved_context()
        notes = MemoryFacade(self.project_root).read_project_notes().strip()[:800]
        summaries = SessionSummaryStore(self.sac_dir).load_recent(limit=3)
        sessions_content = format_memory_context(summaries)
        workspace = WorkspaceMemoryStore(self.project_root).load_all()
        return [
            ContextLedgerItem(
                "approved facts", facts_content, bool(facts_content),
                "explicitly approved project facts are trusted", len(approved),
            ),
            ContextLedgerItem(
                "project notes", f"## Project Notes\n{notes}" if notes else "", bool(notes),
                "trusted project notes and SAC.md are present", 1 if notes else 0,
            ),
            ContextLedgerItem(
                "recent sessions", sessions_content, bool(sessions_content),
                "the three latest bounded summaries preserve continuity", len(summaries),
            ),
            ContextLedgerItem(
                "workspace observations", "", bool(workspace),
                "relevant entries are selected separately by ContextCollector", len(workspace),
            ),
            ContextLedgerItem(
                "pending facts", "", False,
                "requires explicit approval before injection", len(pending),
            ),
        ]

    def injected_context(self) -> str:
        return "\n\n".join(item.content for item in self.collect() if item.injected and item.content)

    def explain(self) -> str:
        lines = ["Memory Context Ledger", "---------------------"]
        for item in self.collect():
            state = "injected" if item.injected else "not injected"
            lines.append(f"- {item.source}: {state} ({item.count})")
            lines.append(f"  Why: {item.reason}.")
        return "\n".join(lines)
