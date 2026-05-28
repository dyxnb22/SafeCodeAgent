"""Tiny local API facade for v1.1 experiments.

This module avoids a web framework dependency. It gives future HTTP adapters a
stable Python-facing interface first.
"""

from pathlib import Path

from safecode.agent.orchestrator import AgentOrchestrator
from safecode.report.render import ReportRenderer


class SafeCodeLocalAPI:
    """Programmatic API over the local runtime."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.orchestrator = AgentOrchestrator(project_root)

    def ask(self, question: str) -> str:
        """Ask a read-only project question."""
        return self.orchestrator.ask(question)

    def report(self) -> str:
        """Render a local task report."""
        return ReportRenderer(self.project_root).render_markdown()
