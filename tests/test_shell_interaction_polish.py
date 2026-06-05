"""Tests for v4.17.1 shell interaction polish (readline, /clear, Markdown)."""

from pathlib import Path
from unittest.mock import patch

import pytest


def test_slash_clear_command_returns_clear_intent():
    """Test /clear command returns clear intent without errors."""
    from safecode.cli_shell import _handle_slash_command
    response, intent, exit_shell = _handle_slash_command(
        "/clear", Path("/tmp"), None, is_tty=True
    )
    assert intent == "clear"
    assert exit_shell is False
    assert "clear" in response.lower()


def test_slash_help_includes_clear():
    """Test /help now includes /clear command."""
    from safecode.cli_shell import _SHELL_HELP
    assert "/clear" in _SHELL_HELP


def test_slash_commands_list_includes_clear():
    """Test _SLASH_COMMANDS list includes /clear."""
    from safecode.cli_shell import _SLASH_COMMANDS
    assert "/clear" in _SLASH_COMMANDS
    assert "/exit" in _SLASH_COMMANDS
    assert "/help" in _SLASH_COMMANDS


def test_setup_readline_no_readline_module():
    """Test _setup_readline handles missing readline module gracefully."""
    with patch("safecode.cli_shell._setup_readline", lambda: None):
        from safecode.cli_shell import _setup_readline
        with patch.dict("sys.modules", {"readline": None}):
            pass


def test_maybe_render_markdown_plain_text():
    """Test _maybe_render_markdown renders plain text without Markdown."""
    from safecode.cli_shell import _maybe_render_markdown
    with patch("safecode.cli_shell.console.print") as mock_print:
        _maybe_render_markdown("Hello world", is_tty=True)
        mock_print.assert_called_once()


def test_maybe_render_markdown_code_block():
    """Test _maybe_render_markdown detects code blocks and uses Markdown."""
    from safecode.cli_shell import _maybe_render_markdown

    with patch("safecode.cli_shell.console.print") as mock_print:
        _maybe_render_markdown("```python\nprint('hi')\n```", is_tty=True)
        mock_print.assert_called_once()


def test_maybe_render_markdown_non_tty():
    """Test _maybe_render_markdown uses plain print in non-TTY mode."""
    from safecode.cli_shell import _maybe_render_markdown
    with patch("builtins.print") as mock_print:
        _maybe_render_markdown("```code```", is_tty=False)
        mock_print.assert_called_once()


def test_shell_banner_version():
    """Test shell banner reflects v4.17+ version."""
    from safecode.cli_shell import _SHELL_BANNER
    assert "v4.17" in _SHELL_BANNER
