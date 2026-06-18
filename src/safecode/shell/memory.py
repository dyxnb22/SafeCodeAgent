"""Shell presentation for the unified memory context ledger."""

from pathlib import Path

from safecode.memory.ledger import ContextLedger


def render_context_ledger(project_root: Path) -> str:
    return ContextLedger(project_root).explain()
