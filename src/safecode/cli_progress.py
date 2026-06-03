"""Optional Rich progress/status indicator for long-running CLI commands (v3.7.1)."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Generator

from rich.console import Console
from rich.status import Status


def _is_tty() -> bool:
    return sys.stdout.isatty()


@contextmanager
def cli_status(message: str, *, console: Console | None = None, tty: bool | None = None) -> Generator[None, None, None]:
    """Show a Rich spinner/status on TTY; emit nothing on non-TTY.

    Usage::
        with cli_status("Running tests..."):
            do_work()
    """
    on_tty = tty if tty is not None else _is_tty()
    if not on_tty:
        yield
        return

    _console = console or Console(stderr=True)
    with _console.status(message, spinner="dots"):
        yield


class StepCounter:
    """Lightweight step counter that emits progress lines on TTY only."""

    def __init__(self, total: int, *, console: Console | None = None, tty: bool | None = None) -> None:
        self._total = total
        self._current = 0
        self._on_tty = tty if tty is not None else _is_tty()
        self._console = console or Console(stderr=True)

    def step(self, label: str) -> None:
        """Advance the counter and print step label on TTY."""
        self._current += 1
        if self._on_tty:
            self._console.print(f"[dim][{self._current}/{self._total}] {label}[/dim]")

    @property
    def current(self) -> int:
        return self._current

    @property
    def total(self) -> int:
        return self._total
