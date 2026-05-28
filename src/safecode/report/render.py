"""Render local SafeCode reports."""

from pathlib import Path

from safecode.audit.logger import AuditLogger


class ReportRenderer:
    """Render a Markdown report from audit events."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def render_markdown(self, limit: int = 50) -> str:
        """Render recent audit events as Markdown."""
        events = AuditLogger(self.project_root).read_recent(limit=limit)
        lines = ["# SafeCode Task Report", ""]
        if not events:
            lines.append("No audit events found.")
            return "\n".join(lines)
        lines.extend(["| Time | Type | Status | Message |", "|---|---|---|---|"])
        for event in events:
            message = (event.message or "").replace("|", "\\|")
            lines.append(f"| {event.timestamp} | {event.type} | {event.status} | {message} |")
        return "\n".join(lines)
