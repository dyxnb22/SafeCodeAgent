"""Rich-rendered unified diff for terminal display (v6.27).

``render_rich_diff(diff_text)`` splits a unified diff into per-file hunks
and renders each one in a colour-coded Rich Panel with a syntax-highlighted
hunk body.

Safety / compatibility:
- Non-TTY: prints plain unified diff text (no Rich markup).
- Empty or non-diff input: prints as-is without crashing.
- Never raises — all errors fall back to plain text output.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

_FILE_HEADER_RE = re.compile(r"^(?:---|\+\+\+|diff --git) ")
_HUNK_HEADER_RE = re.compile(r"^@@ ")


def _parse_file_hunks(diff_text: str) -> list[tuple[str, str]]:
    """Return [(filename, hunk_body)] for each file section in a unified diff."""
    files: list[tuple[str, str]] = []
    current_name = ""
    current_lines: list[str] = []

    for line in diff_text.splitlines(keepends=True):
        if line.startswith("+++ "):
            if current_lines and current_name:
                files.append((current_name, "".join(current_lines)))
            current_name = line[4:].rstrip().lstrip("b/")
            current_lines = []
        elif line.startswith("--- "):
            continue  # skip "---" header; captured by "+++" above
        elif line.startswith("diff --git "):
            if current_lines and current_name:
                files.append((current_name, "".join(current_lines)))
            current_name = ""
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines and current_name:
        files.append((current_name, "".join(current_lines)))

    return files


def _count_changes(hunk_body: str) -> tuple[int, int]:
    added = sum(1 for l in hunk_body.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in hunk_body.splitlines() if l.startswith("-") and not l.startswith("---"))
    return added, removed


def render_rich_diff(
    diff_text: str,
    *,
    title: str = "",
    console: "Console | None" = None,
) -> None:
    """Print a unified diff with Rich colour-coded panels.

    Falls back to plain text when Rich is unavailable, the output is not a TTY,
    or the input is empty / not a real diff.
    """
    if not diff_text or not diff_text.strip():
        return

    _con: Console
    try:
        from rich.console import Console as _Console
        _con = console or _Console()
        if not _con.is_terminal:
            raise RuntimeError("non-tty")
    except Exception:
        # Plain fallback
        if title:
            print(f"=== {title} ===")
        print(diff_text, end="")
        return

    try:
        _render_rich(_con, diff_text, title=title)
    except Exception:
        if title:
            print(f"=== {title} ===")
        print(diff_text, end="")


def _render_rich(con: "Console", diff_text: str, *, title: str) -> None:
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text

    if title:
        con.print(f"[bold]{title}[/bold]")

    file_hunks = _parse_file_hunks(diff_text)

    if not file_hunks:
        # Not a standard unified diff — print as-is.
        con.print(diff_text)
        return

    for fname, hunk_body in file_hunks:
        added, removed = _count_changes(hunk_body)
        header = f"[bold cyan]{fname}[/bold cyan]  [green]+{added}[/green] [red]-{removed}[/red]"
        hunk_syn = Syntax(
            hunk_body,
            "diff",
            theme="monokai",
            line_numbers=False,
            word_wrap=False,
        )
        con.print(Panel(hunk_syn, title=Text.from_markup(header), title_align="left", expand=True))


def format_diff_for_plain(diff_text: str, *, title: str = "") -> str:
    """Return a plain-text formatted diff string (no Rich markup).

    Useful for non-TTY paths and JSON output.
    """
    if not diff_text:
        return ""
    lines = []
    if title:
        lines.append(f"=== {title} ===")
    file_hunks = _parse_file_hunks(diff_text)
    if not file_hunks:
        lines.append(diff_text)
        return "\n".join(lines)
    for fname, hunk_body in file_hunks:
        added, removed = _count_changes(hunk_body)
        lines.append(f"+++ {fname}  (+{added} / -{removed})")
        lines.append(hunk_body)
    return "\n".join(lines)
