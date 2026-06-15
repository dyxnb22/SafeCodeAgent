"""Tests for shell session quality improvements (v4.22.1, EXPERIMENTAL).

Covers B10 (/clear resets AgentSessionStore), B11 (EOF message),
new /undo, /history, /tools slash commands, and sac[N]> prompt.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from safecode.cli_shell import (
    _read_line,
    _shell_prompt,
    _handle_slash_command,
    _SLASH_COMMANDS,
)


# ---------------------------------------------------------------------------
# sac[N]> prompt (v4.22.1)
# ---------------------------------------------------------------------------

def test_shell_prompt_format():
    assert _shell_prompt(0) == "sac[0]> "
    assert _shell_prompt(5) == "sac[5]> "
    assert _shell_prompt(100) == "sac[100]> "


# ---------------------------------------------------------------------------
# B11: EOF message
# ---------------------------------------------------------------------------

def test_b11_eof_tty_prints_exiting_shell(capsys):
    with patch("builtins.input", side_effect=EOFError):
        result = _read_line(is_tty=True, turn=0)
    assert result is None
    captured = capsys.readouterr()
    assert "[exiting shell]" in captured.out


def test_b11_eof_non_tty_prints_exiting_shell(capsys):
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.readline.return_value = ""
        result = _read_line(is_tty=False, turn=0)
    assert result is None
    captured = capsys.readouterr()
    assert "[exiting shell]" in captured.out


def test_read_line_non_eof_returns_text(capsys):
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.readline.return_value = "hello world\n"
        result = _read_line(is_tty=False, turn=3)
    assert result == "hello world"


# ---------------------------------------------------------------------------
# B10: /clear resets AgentSessionStore
# ---------------------------------------------------------------------------

def test_b10_clear_calls_agent_session_store(tmp_path: Path):
    cleared = {"called": False}

    class FakeStore:
        def __init__(self, project_root):
            pass

        def clear(self):
            cleared["called"] = True
            return True

    with patch("safecode.agent.session.AgentSessionStore", FakeStore):
        response, intent, exit_shell = _handle_slash_command(
            "/clear", tmp_path, None, is_tty=False
        )

    assert cleared["called"] is True
    assert "cleared" in response.lower()
    assert intent == "clear"
    assert exit_shell is False


def test_b10_clear_response_always_succeeds(tmp_path: Path):
    # /clear should return success message even when there's no session to clear
    response, intent, _ = _handle_slash_command("/clear", tmp_path, None, is_tty=False)
    assert "cleared" in response.lower()
    assert intent == "clear"


# ---------------------------------------------------------------------------
# /undo slash command
# ---------------------------------------------------------------------------

def test_undo_no_checkpoint(tmp_path: Path):
    response, intent, exit_shell = _handle_slash_command("/undo", tmp_path, None, is_tty=False)
    assert "No checkpoint" in response
    assert intent == "undo"
    assert exit_shell is False


def test_undo_with_checkpoint(tmp_path: Path):
    from safecode.checkpoint.models import CheckpointMetadata, CheckpointFileOperation
    from safecode.utils.time import utc_now_iso

    meta = CheckpointMetadata(
        checkpoint_id="cp-001",
        task="test",
        patch_id="p1",
        created_at=utc_now_iso(),
        file_operations=[CheckpointFileOperation(
            path="src/foo.py",
            operation="update",
            existed_before=True,
            backup_path="files/src/foo.py",
        )],
    )

    with patch("safecode.checkpoint.manager.CheckpointManager.rollback_last", return_value=meta):
        response, intent, _ = _handle_slash_command("/undo", tmp_path, None, is_tty=False)

    assert "cp-001" in response
    assert "src/foo.py" in response
    assert intent == "undo"


# ---------------------------------------------------------------------------
# /history slash command
# ---------------------------------------------------------------------------

def test_history_no_sessions(tmp_path: Path):
    # Without any sessions saved, /history should report no history.
    response, intent, _ = _handle_slash_command("/history", tmp_path, None, is_tty=False)
    assert "No shell session history" in response
    assert intent == "history"


def test_history_with_sessions(tmp_path: Path):
    from safecode.shell_session.store import ShellSessionStore
    from safecode.shell_session.state import ShellTurn
    from safecode.utils.time import utc_now_iso

    # Create a real session with turns.
    store = ShellSessionStore(tmp_path)
    session = store.create()
    turn = ShellTurn(turn_index=0, user_input="hello world", shell_response="hi", intent="ask")
    updated = session.model_copy(update={"turns": [turn], "updated_at": utc_now_iso()})
    store.save(updated)

    response, intent, _ = _handle_slash_command("/history", tmp_path, None, is_tty=False)
    assert intent == "history"
    # The session id or turn content should appear in response
    assert updated.session_id in response or "hello world" in response


# ---------------------------------------------------------------------------
# /tools slash command
# ---------------------------------------------------------------------------

def test_tools_lists_all_native_tools(tmp_path: Path):
    response, intent, exit_shell = _handle_slash_command("/tools", tmp_path, None, is_tty=False)
    assert intent == "tools"
    assert exit_shell is False
    for name in ("read_file", "list_files", "search_files", "grep_files",
                 "edit_file", "write_file", "run_command"):
        assert name in response


def test_tools_marks_approval_required(tmp_path: Path):
    response, _, _ = _handle_slash_command("/tools", tmp_path, None, is_tty=False)
    assert "requires approval" in response.lower()


# ---------------------------------------------------------------------------
# Slash command list includes new commands
# ---------------------------------------------------------------------------

def test_new_slash_commands_in_list():
    for cmd in ("/undo", "/history", "/tools"):
        assert cmd in _SLASH_COMMANDS
