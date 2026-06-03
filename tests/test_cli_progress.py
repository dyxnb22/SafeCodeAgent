"""Tests for CLI progress indicator (v3.7.1 T-3.7.1-B)."""

from __future__ import annotations

import re
from io import StringIO

import pytest
from rich.console import Console

from safecode.cli_progress import StepCounter, cli_status


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestCliStatusNonTTY:
    def test_non_tty_yields_without_output(self, capsys: pytest.CaptureFixture) -> None:
        """cli_status must emit zero extra bytes on non-TTY."""
        executed = False
        with cli_status("Working...", tty=False):
            executed = True
        assert executed
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_non_tty_does_not_raise(self) -> None:
        with cli_status("test", tty=False):
            pass

    def test_non_tty_runs_body_exactly_once(self) -> None:
        count = 0
        with cli_status("msg", tty=False):
            count += 1
        assert count == 1


class TestCliStatusTTY:
    def test_tty_runs_body(self) -> None:
        buf = StringIO()
        console = Console(file=buf, force_terminal=True)
        executed = False
        with cli_status("Processing...", console=console, tty=True):
            executed = True
        assert executed

    def test_tty_does_not_raise_on_exception_inside_body(self) -> None:
        buf = StringIO()
        console = Console(file=buf, force_terminal=True)
        with pytest.raises(ValueError):
            with cli_status("Running", console=console, tty=True):
                raise ValueError("inner error")


class TestStepCounterNonTTY:
    def test_non_tty_emits_nothing(self, capsys: pytest.CaptureFixture) -> None:
        counter = StepCounter(3, tty=False)
        counter.step("Step one")
        counter.step("Step two")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_non_tty_tracks_count(self) -> None:
        counter = StepCounter(5, tty=False)
        assert counter.current == 0
        counter.step("a")
        assert counter.current == 1
        counter.step("b")
        assert counter.current == 2

    def test_total_is_accessible(self) -> None:
        counter = StepCounter(7, tty=False)
        assert counter.total == 7

    def test_counter_starts_at_zero(self) -> None:
        counter = StepCounter(3, tty=False)
        assert counter.current == 0


class TestStepCounterTTY:
    def test_tty_prints_step_labels(self) -> None:
        buf = StringIO()
        console = Console(file=buf, force_terminal=True)
        counter = StepCounter(2, console=console, tty=True)
        counter.step("first step")
        output = buf.getvalue()
        assert "first step" in output

    def test_tty_includes_step_fraction(self) -> None:
        buf = StringIO()
        console = Console(file=buf, force_terminal=True)
        counter = StepCounter(3, console=console, tty=True)
        counter.step("alpha")
        output = _strip_ansi(buf.getvalue())
        assert "1/3" in output

    def test_tty_increments_each_step(self) -> None:
        buf = StringIO()
        console = Console(file=buf, force_terminal=True)
        counter = StepCounter(3, console=console, tty=True)
        counter.step("one")
        counter.step("two")
        output = _strip_ansi(buf.getvalue())
        assert "1/3" in output
        assert "2/3" in output


class TestStepCounterInvariant:
    def test_non_tty_zero_bytes_on_stderr(self, capsys: pytest.CaptureFixture) -> None:
        """Non-TTY must produce zero extra bytes (stdout + stderr)."""
        counter = StepCounter(10, tty=False)
        for i in range(10):
            counter.step(f"step {i}")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
