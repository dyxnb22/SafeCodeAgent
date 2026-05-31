"""Render local SafeCode reports."""

from pathlib import Path

from safecode.audit.logger import AuditLogger
from safecode.state.journal import AgentJournalStore


class ReportRenderer:
    """Render a Markdown report from audit events."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def render_markdown(self, limit: int = 50) -> str:
        """Render recent audit events as Markdown."""
        events = AuditLogger(self.project_root).read_recent(limit=limit)
        lines = ["# SafeCode Task Report", ""]
        journal = AgentJournalStore(self.project_root)
        latest_session_id = journal.latest_session_id()
        if latest_session_id:
            summary = journal.summary(latest_session_id)
            lines.extend(
                [
                    "## Latest Agent Journal",
                    "",
                    f"- Session: `{summary.session_id}`",
                    f"- Events: {summary.event_count}",
                    f"- Last Event: {summary.last_timestamp or '(none)'}",
                    f"- Final Summary: {summary.final_message or '(none)'}",
                    "",
                ]
            )
        if not events:
            lines.append("## Audit Events")
            lines.append("")
            lines.append("No audit events found.")
            return "\n".join(lines)
        lines.extend(["## Audit Events", "", "| Time | Type | Status | Message |", "|---|---|---|---|"])
        for event in events:
            message = (event.message or "").replace("|", "\\|")
            lines.append(f"| {event.timestamp} | {event.type} | {event.status} | {message} |")
        return "\n".join(lines)
