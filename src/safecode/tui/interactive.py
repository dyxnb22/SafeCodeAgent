"""Conservative interactive TUI for SafeCode Agent (experimental).

Does not require Textual. Uses Rich Live display in TTY mode.
In non-TTY mode (piped output), prints a static snapshot and exits 0.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from safecode.tui.dashboard import _build_dashboard


def run_interactive(
    project_root: Path,
    *,
    refresh_seconds: float = 2.0,
    history_limit: int = 8,
) -> None:
    """Run the interactive TUI or static snapshot depending on TTY state.

    Non-TTY: prints one static snapshot and exits (deterministic/CI-safe).
    TTY: refreshes every *refresh_seconds*; Ctrl-C exits cleanly.
    """
    if not sys.stdout.isatty():
        _print_static(project_root, history_limit=history_limit)
        return

    _run_live(project_root, refresh_seconds=refresh_seconds, history_limit=history_limit)


def _print_static(project_root: Path, *, history_limit: int) -> None:
    """Render one static dashboard snapshot to stdout (non-TTY / test mode)."""
    from rich.console import Console

    console = Console(record=True, width=120)
    panel = _build_dashboard(project_root, history_limit=history_limit)
    console.print(panel)
    sys.stdout.write(console.export_text())
    sys.stdout.flush()


def _run_live(
    project_root: Path,
    *,
    refresh_seconds: float,
    history_limit: int,
) -> None:
    """Run a refreshing Rich Live panel in TTY mode."""
    from rich.console import Console
    from rich.live import Live

    console = Console()
    try:
        with Live(
            _build_dashboard(project_root, history_limit=history_limit),
            console=console,
            refresh_per_second=max(1, int(1.0 / max(0.1, refresh_seconds))),
        ) as live:
            while True:
                time.sleep(refresh_seconds)
                live.update(_build_dashboard(project_root, history_limit=history_limit))
    except KeyboardInterrupt:
        pass
