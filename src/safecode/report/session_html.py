"""Per-session HTML report renderer (v3.6.3).

Renders a deterministic, self-contained HTML page from the journal data for one
agent session.  No external network assets.  Secrets are redacted before rendering.
Handles missing and empty sessions gracefully.
"""

from __future__ import annotations

import html as _html_mod
from dataclasses import dataclass
from pathlib import Path

from safecode.context.redactor import redact_secrets
from safecode.state.journal import AgentJournalStore


_CSS = (
    "body{font-family:sans-serif;margin:2em;color:#222}\n"
    "table{border-collapse:collapse;margin-bottom:1em}\n"
    "th,td{border:1px solid #ccc;padding:.4em .8em;text-align:left}\n"
    "th{background:#f0f0f0}\n"
    "h1{border-bottom:2px solid #ccc;padding-bottom:.3em}\n"
    "h2{margin-top:1.5em}\n"
    ".plan{color:#2a7a2a}\n"
    ".failure{color:#b00}\n"
    ".final_summary{font-style:italic}\n"
    "code{background:#f4f4f4;padding:.1em .3em;border-radius:3px}\n"
)


@dataclass(frozen=True)
class SessionHtmlReport:
    """Outcome of rendering one session as HTML."""

    session_id: str
    html: str
    event_count: int
    found: bool


def render_session_html(session_id: str, project_root: Path) -> SessionHtmlReport:
    """Render a per-session HTML report from journal data.

    Always returns a valid HTML string — missing or empty sessions produce a
    human-readable page rather than an error.  Secrets in journal messages are
    redacted via ``redact_secrets`` before being embedded in the HTML.

    The output is deterministic: identical inputs always produce identical HTML.
    No external stylesheets, scripts, or fonts are referenced.
    """
    e = _html_mod.escape
    store = AgentJournalStore(project_root)

    if not store._is_valid_session_id(session_id):
        html = _error_html(f"Invalid session id: {e(session_id[:64])}")
        return SessionHtmlReport(session_id=session_id, html=html, event_count=0, found=False)

    events = store.read(session_id)
    title = f"SafeCode Session: {session_id}"

    parts: list[str] = [
        "<!DOCTYPE html>\n",
        '<html lang="en">\n',
        "<head>\n",
        '<meta charset="utf-8">\n',
        f"<title>{e(title)}</title>\n",
        f"<style>\n{_CSS}</style>\n",
        "</head>\n",
        "<body>\n",
        f"<h1>{e(title)}</h1>\n",
    ]

    if not events:
        parts.append(
            f"<p><em>No journal events found for session "
            f"<code>{e(session_id)}</code>.</em></p>\n"
        )
        parts.append("</body>\n</html>")
        return SessionHtmlReport(
            session_id=session_id,
            html="".join(parts),
            event_count=0,
            found=False,
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    first_ts = events[0].timestamp
    last_ts = events[-1].timestamp
    final_message = next(
        (ev.message for ev in reversed(events) if ev.type == "final_summary"),
        None,
    )

    parts.append("<h2>Summary</h2>\n<ul>\n")
    parts.append(f"<li><strong>Session ID:</strong> <code>{e(session_id)}</code></li>\n")
    parts.append(f"<li><strong>Events:</strong> {len(events)}</li>\n")
    parts.append(f"<li><strong>First event:</strong> {e(first_ts)}</li>\n")
    parts.append(f"<li><strong>Last event:</strong> {e(last_ts)}</li>\n")
    if final_message is not None:
        parts.append(
            f"<li><strong>Final summary:</strong> {e(redact_secrets(final_message))}</li>\n"
        )
    parts.append("</ul>\n")

    # ── Events table ──────────────────────────────────────────────────────────
    parts.append("<h2>Journal Events</h2>\n")
    parts.append(
        "<table>\n"
        "<tr><th>Timestamp</th><th>Type</th><th>Step</th><th>Message</th></tr>\n"
    )
    for event in events:
        redacted_msg = redact_secrets(event.message)
        step_str = str(event.step) if event.step is not None else ""
        type_class = e(event.type)
        parts.append(
            f"<tr>"
            f"<td>{e(event.timestamp)}</td>"
            f'<td class="{type_class}">{e(event.type)}</td>'
            f"<td>{e(step_str)}</td>"
            f"<td>{e(redacted_msg)}</td>"
            f"</tr>\n"
        )
    parts.append("</table>\n")

    parts.append("</body>\n</html>")
    return SessionHtmlReport(
        session_id=session_id,
        html="".join(parts),
        event_count=len(events),
        found=True,
    )


def _error_html(message: str) -> str:
    """Minimal error HTML page (inputs must already be escaped by the caller)."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head><meta charset=\"utf-8\"><title>SafeCode Report Error</title></head>\n"
        f"<body><p><strong>Error:</strong> {message}</p></body>\n"
        "</html>"
    )
