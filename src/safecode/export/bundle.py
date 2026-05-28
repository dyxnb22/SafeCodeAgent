"""Export local reports and runtime metadata."""

from pathlib import Path

from safecode.report.render import ReportRenderer


class Exporter:
    """Export SafeCode artifacts to files."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def report(self, output: Path) -> Path:
        """Write a Markdown report to output."""
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(ReportRenderer(self.project_root).render_markdown(), encoding="utf-8")
        return output
