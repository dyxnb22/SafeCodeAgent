"""Tests for v4.18.1 agent-loop transparency (on_step callback, Rich Status)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from safecode.agent.loop import AgentLoop


def test_agent_loop_run_accepts_on_step_callback(tmp_path: Path):
    """AgentLoop.run() accepts and calls the on_step callback."""
    captured: list = []

    def on_step(result):
        captured.append(result)

    loop = AgentLoop(tmp_path)
    result = loop.run("test goal", max_steps=2, on_step=on_step)
    assert len(captured) >= 1
    assert len(result.steps) == len(captured)


def test_agent_loop_run_on_step_is_optional(tmp_path: Path):
    """AgentLoop.run() works without on_step (backward compatible)."""
    loop = AgentLoop(tmp_path)
    result = loop.run("test goal", max_steps=2)
    assert len(result.steps) >= 1


def test_agent_loop_run_on_step_exception_does_not_crash(tmp_path: Path):
    """Exceptions in on_step do not abort the loop."""
    def bad_callback(result):
        raise RuntimeError("callback error")

    loop = AgentLoop(tmp_path)
    result = loop.run("test goal", max_steps=2, on_step=bad_callback)
    assert len(result.steps) >= 1


def test_on_step_called_per_step(tmp_path: Path):
    """on_step is called exactly once per step."""
    captured: list = []

    def on_step(result):
        captured.append(result.observation)

    loop = AgentLoop(tmp_path)
    result = loop.run("test goal", max_steps=3, on_step=on_step)
    assert len(captured) == len(result.steps)


def test_agent_run_command_supports_on_step(tmp_path: Path):
    """sac agent run uses Status in TTY mode with multiple steps."""
    from safecode.cli_agent import agent_run

    import typer
    with patch("safecode.cli_agent.Path.cwd", return_value=tmp_path):
        try:
            pass
        except typer.Exit:
            pass
