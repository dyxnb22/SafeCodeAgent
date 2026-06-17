"""Tests for v6.28: AI-generated commit message (sac commit --ai)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from safecode.agent.schemas import AgentAnswer
from safecode.cli_commit import _generate_ai_commit_message


# ---------------------------------------------------------------------------
# _generate_ai_commit_message unit tests
# ---------------------------------------------------------------------------

class TestGenerateAICommitMessage:
    def _mock_llm(self, message: str) -> MagicMock:
        client = MagicMock()
        client.ask.return_value = AgentAnswer(content=message)
        return client

    def test_returns_string(self, tmp_path):
        msg = "fix(parser): handle None input in parse_config"
        with patch("safecode.cli_commit.create_llm_client", return_value=self._mock_llm(msg)):
            result = _generate_ai_commit_message(tmp_path, "fix parse_config", ["src/parser.py"])
        assert result == msg

    def test_llm_called_once(self, tmp_path):
        llm = self._mock_llm("fix: patch")
        with patch("safecode.cli_commit.create_llm_client", return_value=llm):
            _generate_ai_commit_message(tmp_path, "goal", ["a.py"])
        assert llm.ask.call_count == 1

    def test_task_goal_in_prompt(self, tmp_path):
        llm = self._mock_llm("fix: something")
        with patch("safecode.cli_commit.create_llm_client", return_value=llm):
            _generate_ai_commit_message(tmp_path, "unique-goal-xyz-123", ["src/foo.py"])
        prompt = llm.ask.call_args[0][0]
        assert "unique-goal-xyz-123" in prompt

    def test_file_names_in_prompt(self, tmp_path):
        llm = self._mock_llm("fix: something")
        with patch("safecode.cli_commit.create_llm_client", return_value=llm):
            _generate_ai_commit_message(tmp_path, "goal", ["src/parser.py", "tests/test_parser.py"])
        prompt = llm.ask.call_args[0][0]
        assert "parser.py" in prompt

    def test_empty_llm_response_raises(self, tmp_path):
        llm = MagicMock()
        llm.ask.return_value = AgentAnswer(content="")
        with patch("safecode.cli_commit.create_llm_client", return_value=llm):
            with pytest.raises(ValueError, match="empty"):
                _generate_ai_commit_message(tmp_path, "goal", ["a.py"])

    def test_llm_error_propagates(self, tmp_path):
        llm = MagicMock()
        llm.ask.side_effect = RuntimeError("provider down")
        with patch("safecode.cli_commit.create_llm_client", return_value=llm):
            with pytest.raises(RuntimeError, match="provider down"):
                _generate_ai_commit_message(tmp_path, "goal", ["a.py"])

    def test_diff_capped_in_prompt(self, tmp_path):
        llm = self._mock_llm("fix: something")
        big_diff = "+" * 10000
        with patch("safecode.cli_commit.create_llm_client", return_value=llm), \
             patch("safecode.cli_commit.diff_for_files", return_value=big_diff):
            _generate_ai_commit_message(tmp_path, "goal", ["a.py"])
        prompt = llm.ask.call_args[0][0]
        # Prompt should not contain the full 10K diff
        assert len(prompt) < 6000

    def test_secrets_redacted_from_diff(self, tmp_path):
        llm = self._mock_llm("fix: something")
        diff_with_secret = "+API_KEY=sk-test-secret-key-1234567890abcdef"
        with patch("safecode.cli_commit.create_llm_client", return_value=llm), \
             patch("safecode.cli_commit.diff_for_files", return_value=diff_with_secret):
            _generate_ai_commit_message(tmp_path, "goal", ["a.py"])
        prompt = llm.ask.call_args[0][0]
        assert "sk-test-secret-key-1234567890abcdef" not in prompt

    def test_many_files_truncated_in_prompt(self, tmp_path):
        llm = self._mock_llm("fix: something")
        files = [f"src/file{i}.py" for i in range(50)]
        with patch("safecode.cli_commit.create_llm_client", return_value=llm):
            _generate_ai_commit_message(tmp_path, "goal", files)
        prompt = llm.ask.call_args[0][0]
        assert "more" in prompt  # truncation notice


# ---------------------------------------------------------------------------
# CLI integration: --dry-run
# ---------------------------------------------------------------------------

class TestCommitAICLI:
    def test_dry_run_does_not_commit(self, tmp_path):
        """--ai --dry-run should print message and exit without committing."""
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        # This would fail before reaching commit because no git repo / task
        # but we verify the flag is accepted
        result = runner.invoke(app, ["commit", "--ai", "--dry-run", "--json"])
        # Expect exit 1 (no git repo / task) — not a crash with "Type not supported"
        assert result.exit_code in (0, 1)
        # Should not be a Typer type-annotation crash
        if result.exception:
            assert "Type not yet supported" not in str(result.exception)
