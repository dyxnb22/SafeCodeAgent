"""Tests for run_command native tool (v4.21.1, EXPERIMENTAL)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from safecode.agent.command_tool import (
    _run_command_handler,
    register_command_tool,
    RUN_COMMAND_SPEC,
)
from safecode.agent.native_dispatcher import NativeToolDispatcher
from safecode.agent.native_tools import NativeToolCall
from safecode.shell.runner import ShellRunResult, ShellRisk


def _inp(project_root: Path, **kwargs):
    return {"_project_root": str(project_root), **kwargs}


def _mock_result(command="echo hi", executed=True, exit_code=0, stdout="hi", stderr="",
                 risk_level="low") -> ShellRunResult:
    risk = MagicMock(spec=ShellRisk)
    risk.level = risk_level
    risk.tokens = []
    return ShellRunResult(
        command=command,
        risk=risk,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=5,
        executed=executed,
    )


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

def test_run_command_spec():
    assert RUN_COMMAND_SPEC.name == "run_command"
    assert RUN_COMMAND_SPEC.requires_approval is False
    assert RUN_COMMAND_SPEC.audit_event_type == "tool_call_command"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

def test_missing_command(tmp_path: Path):
    result = _run_command_handler("c1", _inp(tmp_path))
    assert result.status == "error"
    assert "command" in result.error.lower()


def test_cwd_outside_root_blocked(tmp_path: Path):
    result = _run_command_handler("c1", _inp(tmp_path, command="ls", cwd="../../"))
    assert result.status == "blocked"
    assert "outside" in result.error.lower()


# ---------------------------------------------------------------------------
# ShellRunner integration (mocked)
# ---------------------------------------------------------------------------

def test_successful_command(tmp_path: Path):
    mock_result = _mock_result(exit_code=0, stdout="hello", executed=True)
    with patch("safecode.agent.command_tool.ShellRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run.return_value = mock_result
        result = _run_command_handler("c1", _inp(tmp_path, command="echo hello"))
    assert result.status == "success"
    assert "hello" in result.output
    assert result.metadata["exit_code"] == 0


def test_high_risk_command_blocked(tmp_path: Path):
    mock_result = _mock_result(executed=False, exit_code=126, stderr="policy blocked")
    with patch("safecode.agent.command_tool.ShellRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run.return_value = mock_result
        result = _run_command_handler("c1", _inp(tmp_path, command="rm -rf /"))
    assert result.status == "blocked"


def test_command_with_nonzero_exit(tmp_path: Path):
    mock_result = _mock_result(exit_code=1, stdout="", stderr="error msg", executed=True)
    with patch("safecode.agent.command_tool.ShellRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run.return_value = mock_result
        result = _run_command_handler("c1", _inp(tmp_path, command="false"))
    assert result.status == "success"
    assert result.metadata["exit_code"] == 1


def test_cwd_inside_project(tmp_path: Path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    mock_result = _mock_result(exit_code=0, stdout="ok", executed=True)
    with patch("safecode.agent.command_tool.ShellRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run.return_value = mock_result
        result = _run_command_handler("c1", _inp(tmp_path, command="pwd", cwd="subdir"))
    assert result.status == "success"


def test_result_includes_duration(tmp_path: Path):
    mock_result = _mock_result(exit_code=0, stdout="x", executed=True)
    mock_result = ShellRunResult(
        command="echo x", risk=mock_result.risk, exit_code=0,
        stdout="x", stderr="", duration_ms=42, executed=True
    )
    with patch("safecode.agent.command_tool.ShellRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run.return_value = mock_result
        result = _run_command_handler("c1", _inp(tmp_path, command="echo x"))
    assert result.metadata.get("duration_ms") == 42


# ---------------------------------------------------------------------------
# register_command_tool integration
# ---------------------------------------------------------------------------

def test_register_command_tool_wires_tool(tmp_path: Path):
    dispatcher = NativeToolDispatcher()
    register_command_tool(dispatcher, tmp_path)
    names = {s.name for s in dispatcher.specs()}
    assert "run_command" in names


def test_registered_tool_dispatches(tmp_path: Path):
    mock_result = _mock_result(exit_code=0, stdout="dispatched", executed=True)
    with patch("safecode.agent.command_tool.ShellRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run.return_value = mock_result
        dispatcher = NativeToolDispatcher()
        register_command_tool(dispatcher, tmp_path)
        call = NativeToolCall(tool_name="run_command", input={"command": "echo hi"}, call_id="c1")
        result = dispatcher.dispatch(call)
    assert result.status == "success"
