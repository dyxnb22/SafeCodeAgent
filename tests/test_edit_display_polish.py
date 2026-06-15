"""Tests for v5.2.1 edit display polish: compact diff header, output collapsing, prompt."""

from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# Compact diff header (v5.2.1)
# ---------------------------------------------------------------------------

class TestCompactDiffHeader:
    def test_diff_has_plus_minus_header(self):
        from safecode.agent.write_tools import _compact_diff
        old = "line1\nline2\nline3\n"
        new = "line1\nline2_new\nline3\nadded\n"
        result = _compact_diff(old, new, "src/foo.py")
        assert "[+" in result
        assert "/ -" in result
        assert "src/foo.py" in result

    def test_diff_header_first_line(self):
        from safecode.agent.write_tools import _compact_diff
        old = "x = 1\n"
        new = "x = 2\n"
        result = _compact_diff(old, new, "foo.py")
        lines = result.splitlines()
        assert lines[0].startswith("[+")
        assert "foo.py" in lines[0]

    def test_diff_counts_correct_lines(self):
        from safecode.agent.write_tools import _compact_diff
        old = "a\nb\nc\n"
        new = "a\nB\nC\nd\n"
        result = _compact_diff(old, new, "test.py")
        # 2 lines removed (b, c), 3 lines added (B, C, d)
        assert "[+3 / -2 lines]" in result

    def test_diff_no_change_shows_zero_zero(self):
        from safecode.agent.write_tools import _compact_diff
        text = "unchanged\n"
        result = _compact_diff(text, text, "same.py")
        # No diff lines — unified_diff produces nothing meaningful
        assert "[+0 / -0 lines]" in result


# ---------------------------------------------------------------------------
# Command output collapsing (v5.2.1)
# ---------------------------------------------------------------------------

class TestCommandOutputCollapsing:
    def test_short_output_not_collapsed(self):
        from safecode.agent.command_tool import _collapse_output
        output = "\n".join(f"line {i}" for i in range(10))
        assert _collapse_output(output) == output

    def test_long_output_collapsed(self):
        from safecode.agent.command_tool import _collapse_output
        output = "\n".join(f"line {i}" for i in range(50))
        result = _collapse_output(output)
        assert "lines hidden" in result
        assert "line 0" in result   # first line visible
        assert "line 49" in result  # last line visible

    def test_collapsed_shows_5_head_5_tail(self):
        from safecode.agent.command_tool import _collapse_output
        output = "\n".join(f"line {i}" for i in range(60))
        result = _collapse_output(output)
        lines = result.splitlines()
        assert lines[0] == "line 0"
        assert lines[4] == "line 4"
        assert "hidden" in lines[5]
        assert lines[-1] == "line 59"

    def test_exactly_40_lines_not_collapsed(self):
        from safecode.agent.command_tool import _collapse_output
        output = "\n".join(f"line {i}" for i in range(40))
        assert _collapse_output(output) == output

    def test_41_lines_collapsed(self):
        from safecode.agent.command_tool import _collapse_output
        output = "\n".join(f"line {i}" for i in range(41))
        result = _collapse_output(output)
        assert "hidden" in result

    def test_run_command_metadata_includes_collapsed_flag(self, tmp_path):
        """NativeToolResult includes output_collapsed=True when output is long."""
        from safecode.agent.command_tool import _run_command_handler
        from unittest.mock import MagicMock, patch

        long_output = "\n".join(f"line {i}" for i in range(50))
        mock_result = MagicMock()
        mock_result.executed = True
        mock_result.exit_code = 0
        mock_result.stdout = long_output
        mock_result.stderr = ""
        mock_result.duration_ms = 100

        with patch("safecode.shell.runner.ShellRunner.run", return_value=mock_result):
            result = _run_command_handler("c1", {
                "_project_root": str(tmp_path),
                "command": "longcmd",
            })

        assert result.status == "success"
        assert result.metadata.get("output_collapsed") is True
        assert "hidden" in (result.output or "")

    def test_run_command_metadata_collapsed_false_for_short(self, tmp_path):
        """Short output: output_collapsed=False."""
        from safecode.agent.command_tool import _run_command_handler
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.executed = True
        mock_result.exit_code = 0
        mock_result.stdout = "short output"
        mock_result.stderr = ""
        mock_result.duration_ms = 5

        with patch("safecode.shell.runner.ShellRunner.run", return_value=mock_result):
            result = _run_command_handler("c2", {
                "_project_root": str(tmp_path),
                "command": "echo short",
            })

        assert result.metadata.get("output_collapsed") is False


# ---------------------------------------------------------------------------
# Shell prompt with task status (v5.2.1)
# ---------------------------------------------------------------------------

class TestShellPromptTaskStatus:
    def test_prompt_with_task_str(self):
        from safecode.cli_shell import _shell_prompt
        prompt = _shell_prompt(3, task_str="task:open · 2i")
        assert "sac[3 · task:open · 2i]>" in prompt

    def test_prompt_with_cost_and_task(self):
        from safecode.cli_shell import _shell_prompt
        prompt = _shell_prompt(5, cost_str="~$0.02", task_str="task:acti · 0i")
        assert "sac[5 · task:acti · 0i · ~$0.02]>" in prompt

    def test_prompt_without_task_str(self):
        from safecode.cli_shell import _shell_prompt
        prompt = _shell_prompt(2)
        assert prompt == "sac[2]> "

    def test_prompt_with_cost_only(self):
        from safecode.cli_shell import _shell_prompt
        prompt = _shell_prompt(1, cost_str="~$0.01")
        assert "sac[1 · ~$0.01]>" in prompt
