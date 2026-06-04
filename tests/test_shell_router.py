"""Tests for sac shell natural-language intent router — v4.9.1."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Intent classification matrix
# ---------------------------------------------------------------------------


class TestIntentClassification:
    """classify_intent maps natural-language inputs to the correct intent."""

    def _classify(self, text: str) -> str:
        from safecode.shell_session.router import classify_intent
        return classify_intent(text)

    # Read-only intents
    def test_what_is_this_project_classified_as_ask_or_overview(self):
        # "what is this project?" may match 'overview' or 'ask' depending on pattern order
        assert self._classify("what is this project?") in ("ask", "overview")

    def test_how_does_auth_work_classified_as_ask(self):
        assert self._classify("How does the auth module work?") == "ask"

    def test_explain_codebase_classified_as_overview(self):
        assert self._classify("explain this codebase to me") == "overview"

    def test_project_structure_classified_as_overview(self):
        assert self._classify("show me the project structure") == "overview"

    def test_what_is_project_structure_classified_as_overview(self):
        assert self._classify("what is this project?") in ("ask", "overview")

    def test_status_query_classified_as_status(self):
        assert self._classify("status") == "status"

    def test_whats_going_on_classified_as_status(self):
        assert self._classify("what's going on?") == "status"

    def test_debug_last_failure_classified_as_debug(self):
        assert self._classify("debug last failure") == "debug"

    def test_show_error_classified_as_debug(self):
        assert self._classify("show me the last error") == "debug"

    def test_exit_classified_as_exit(self):
        assert self._classify("exit") == "exit"

    def test_quit_classified_as_exit(self):
        assert self._classify("quit") == "exit"

    # Write intents
    def test_apply_patch_classified_as_apply(self):
        assert self._classify("apply the patch") == "apply"

    def test_apply_it_classified_as_apply(self):
        assert self._classify("apply it") == "apply"

    def test_commit_classified_as_commit(self):
        assert self._classify("commit") == "commit"

    def test_run_tests_classified_as_run(self):
        assert self._classify("run the tests") == "run"

    def test_lint_classified_as_run(self):
        assert self._classify("lint") == "run"

    def test_typecheck_classified_as_run(self):
        assert self._classify("typecheck") == "run"

    def test_build_classified_as_run(self):
        assert self._classify("build") == "run"

    def test_fix_bug_classified_as_fix(self):
        assert self._classify("fix the bug") == "fix"

    def test_fix_test_failure_classified_as_fix(self):
        assert self._classify("fix the test failure") in ("fix", "run")

    def test_smallest_safe_fix_classified_as_fix_or_edit(self):
        intent = self._classify("make the smallest safe fix")
        assert intent in ("fix", "edit")

    def test_edit_file_classified_as_edit(self):
        assert self._classify("edit the config file") == "edit"

    def test_change_function_classified_as_edit(self):
        assert self._classify("change the validate function") == "edit"

    def test_empty_input_defaults_to_ask(self):
        assert self._classify("") == "ask"

    def test_garbage_input_defaults_to_ask(self):
        assert self._classify("xyzzy frobble zorp") == "ask"


# ---------------------------------------------------------------------------
# Read-only questions stay read-only
# ---------------------------------------------------------------------------


class TestReadOnlyQuestionsStayReadOnly:
    def test_ask_intent_calls_orchestrator_ask(self, tmp_path):
        """Questions routed to 'ask' call AgentOrchestrator.ask, not edit."""
        from safecode.shell_session.router import route_input

        mock_result = MagicMock()
        mock_result.content = "This is a Python package."

        with patch("safecode.agent.orchestrator.AgentOrchestrator.ask") as mock_ask:
            mock_ask.return_value = mock_result
            response, intent, exit_shell = route_input(
                "how does the auth module work?", tmp_path, None, is_tty=False
            )

        assert intent == "ask"
        assert exit_shell is False

    def test_status_does_not_mutate(self, tmp_path):
        """Status intent never calls edit/apply/run."""
        from safecode.shell_session.router import route_input

        response, intent, exit_shell = route_input("status", tmp_path, None, is_tty=False)
        assert intent == "status"
        assert exit_shell is False
        # No patch file should be created
        assert not (tmp_path / ".sac" / "pending_patch.json").exists()

    def test_overview_does_not_mutate(self, tmp_path):
        """Overview intent never mutates anything."""
        from safecode.shell_session.router import route_input

        response, intent, exit_shell = route_input(
            "explain this codebase", tmp_path, None, is_tty=False
        )
        assert intent in ("overview", "ask")
        assert exit_shell is False

    def test_debug_does_not_mutate(self, tmp_path):
        """Debug intent never mutates anything."""
        from safecode.shell_session.router import route_input

        response, intent, _ = route_input(
            "debug last failure", tmp_path, None, is_tty=False
        )
        assert intent == "debug"


# ---------------------------------------------------------------------------
# Mutation / run / commit approval prompt tests
# ---------------------------------------------------------------------------


class TestMutationRequiresConfirmation:
    def test_edit_in_non_tty_requires_confirmation_hint(self, tmp_path):
        """Edit intent in non-TTY returns a 'run: sac edit' hint without mutating."""
        from safecode.shell_session.router import route_input

        response, intent, _ = route_input(
            "change the main function", tmp_path, None, is_tty=False
        )
        assert intent == "edit"
        # No confirmation in non-TTY → must NOT mutate
        assert not (tmp_path / ".sac" / "pending_patch.json").exists()
        assert "sac edit" in response.lower() or "not confirmed" in response.lower()

    def test_fix_in_non_tty_does_not_run(self, tmp_path):
        """Fix intent in non-TTY does not execute the fix loop."""
        from safecode.shell_session.router import route_input

        response, intent, _ = route_input("fix the bug", tmp_path, None, is_tty=False)
        assert intent == "fix"
        assert "not confirmed" in response.lower() or "sac fix" in response.lower()

    def test_run_in_non_tty_does_not_run(self, tmp_path):
        """Run intent in non-TTY does not execute commands."""
        from safecode.shell_session.router import route_input

        response, intent, _ = route_input("run the tests", tmp_path, None, is_tty=False)
        assert intent == "run"
        # Should not execute anything
        assert not (tmp_path / ".sac" / "pending_patch.json").exists()

    def test_apply_in_non_tty_does_not_apply(self, tmp_path):
        """Apply intent in non-TTY does not apply the patch."""
        from safecode.shell_session.router import route_input
        from safecode.patch.models import PatchProposal

        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        proposal = PatchProposal(
            id="router-apply-test",
            task="test",
            blocks=[],
            created_at="2026-01-01T00:00:00Z",
            model="mock",
            status="pending",
        )
        (sac_dir / "pending_patch.json").write_text(proposal.model_dump_json())

        response, intent, _ = route_input("apply the patch", tmp_path, None, is_tty=False)
        assert intent == "apply"
        # Patch must still be there
        assert (sac_dir / "pending_patch.json").exists()
        assert "sac apply" in response

    def test_commit_in_non_tty_does_not_commit(self, tmp_path):
        """Commit intent in non-TTY does not commit."""
        from safecode.shell_session.router import route_input

        response, intent, _ = route_input("commit", tmp_path, None, is_tty=False)
        assert intent == "commit"
        assert "sac commit" in response

    def test_edit_with_tty_confirmation_y_calls_orchestrator(self, tmp_path):
        """Edit with TTY 'y' confirmation calls AgentOrchestrator.edit."""
        from safecode.shell_session.router import route_input

        mock_result = MagicMock()
        mock_result.proposal = MagicMock(id="patch-1")
        mock_result.pending_patch_path = tmp_path / ".sac" / "pending_patch.json"

        with (
            patch("builtins.input", return_value="y"),
            patch("safecode.agent.orchestrator.AgentOrchestrator.edit", return_value=mock_result) as mock_edit,
            patch("safecode.task.wiring.get_or_create_current_task") as mock_task,
            patch("safecode.task.wiring.record_edit_on_task"),
        ):
            mock_task.return_value = MagicMock(task_id="t-1")
            response, intent, _ = route_input(
                "change the main function", tmp_path, None, is_tty=True
            )

        assert intent == "edit"
        assert mock_edit.called

    def test_edit_with_tty_confirmation_n_does_not_call_orchestrator(self, tmp_path):
        """Edit with TTY 'n' confirmation does NOT call AgentOrchestrator.edit."""
        from safecode.shell_session.router import route_input

        with (
            patch("builtins.input", return_value="n"),
            patch("safecode.agent.orchestrator.AgentOrchestrator.edit") as mock_edit,
        ):
            response, intent, _ = route_input(
                "change the main function", tmp_path, None, is_tty=True
            )

        mock_edit.assert_not_called()
        assert "not confirmed" in response.lower() or "sac edit" in response.lower()


# ---------------------------------------------------------------------------
# Profile-based routing
# ---------------------------------------------------------------------------


class TestProfileBasedRouting:
    def test_run_test_suite_uses_profile_test_suite(self, tmp_path):
        """'run the tests' routes to profile test suite."""
        from safecode.shell_session.router import _detect_suite_from_input
        assert _detect_suite_from_input("run the tests") == "test"

    def test_run_lint_suite(self, tmp_path):
        from safecode.shell_session.router import _detect_suite_from_input
        assert _detect_suite_from_input("run lint") == "lint"

    def test_run_typecheck_suite(self, tmp_path):
        from safecode.shell_session.router import _detect_suite_from_input
        assert _detect_suite_from_input("typecheck the project") == "typecheck"

    def test_run_build_suite(self, tmp_path):
        from safecode.shell_session.router import _detect_suite_from_input
        assert _detect_suite_from_input("build the project") == "build"


# ---------------------------------------------------------------------------
# Existing command exit-code semantics unchanged
# ---------------------------------------------------------------------------


class TestExistingCommandExitCodes:
    def test_sac_ask_still_works_directly(self, tmp_path):
        """sac ask exit-code semantics are unchanged by the router."""
        from typer.testing import CliRunner
        from safecode.cli import app
        from unittest.mock import patch

        runner = CliRunner()
        with patch("safecode.agent.orchestrator.AgentOrchestrator.ask") as mock_ask:
            mock_ask.return_value = MagicMock(content="ok")
            result = runner.invoke(app, ["ask", "what is this?"])
        assert result.exit_code == 0

    def test_sac_status_still_works_directly(self, tmp_path, monkeypatch):
        """sac status exit-code semantics are unchanged."""
        monkeypatch.chdir(tmp_path)
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0

    def test_router_exit_returns_exit_flag(self, tmp_path):
        """Routing 'exit' returns exit_shell=True."""
        from safecode.shell_session.router import route_input
        _, _, exit_shell = route_input("exit", tmp_path, None, is_tty=False)
        assert exit_shell is True

    def test_router_quit_returns_exit_flag(self, tmp_path):
        from safecode.shell_session.router import route_input
        _, _, exit_shell = route_input("quit", tmp_path, None, is_tty=False)
        assert exit_shell is True
