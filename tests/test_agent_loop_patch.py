"""v2.3.6: AgentLoop patch proposal path tests.

AgentLoop can produce pending patch proposals and stop for approval.
Target files are not modified until the user explicitly runs 'sac apply'.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.agent.loop import AgentLoop
from safecode.agent.orchestrator import AgentOrchestrator
from safecode.cli import app

runner = CliRunner()

_CALCULATOR_BUGGY = """\
def add(left: int, right: int) -> int:
    \"\"\"Return the sum of two integers.\"\"\"
    return left - right + 0
"""


def _setup_calculator(tmp_path: Path) -> Path:
    """Create a minimal project with a buggy calculator file."""
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    calc = src / "calculator.py"
    calc.write_text(_CALCULATOR_BUGGY, encoding="utf-8")
    return calc


class TestAgentLoopPatchPath:
    def test_run_creates_pending_patch(self, tmp_path):
        _setup_calculator(tmp_path)
        AgentLoop(tmp_path).run("fix calculator bug", max_steps=3)
        assert (tmp_path / ".sac" / "pending_patch.json").exists()

    def test_run_stops_with_approval_required(self, tmp_path):
        _setup_calculator(tmp_path)
        result = AgentLoop(tmp_path).run("fix calculator bug", max_steps=3)
        assert result.stopped_reason == "approval_required"

    def test_session_status_is_waiting_for_user(self, tmp_path):
        _setup_calculator(tmp_path)
        result = AgentLoop(tmp_path).run("fix calculator bug", max_steps=3)
        assert result.state.status == "waiting_for_user"

    def test_target_file_not_modified_before_apply(self, tmp_path):
        calc = _setup_calculator(tmp_path)
        original = calc.read_text(encoding="utf-8")
        AgentLoop(tmp_path).run("fix calculator bug", max_steps=3)
        assert calc.read_text(encoding="utf-8") == original

    def test_pending_action_indicates_patch_proposal(self, tmp_path):
        _setup_calculator(tmp_path)
        result = AgentLoop(tmp_path).run("fix calculator bug", max_steps=3)
        action = result.state.pending_action
        assert action is not None
        assert action["type"] == "patch"
        assert action.get("requires_approval") == "true"
        assert "pending_patch_path" in action
        assert "patch_id" in action

    def test_pending_action_lists_target_files(self, tmp_path):
        _setup_calculator(tmp_path)
        result = AgentLoop(tmp_path).run("fix calculator bug", max_steps=3)
        files = result.state.pending_action["files"]
        assert isinstance(files, list)
        assert any("calculator" in f for f in files)

    def test_pending_patch_already_exists_fails_closed(self, tmp_path):
        _setup_calculator(tmp_path)
        sac = tmp_path / ".sac"
        sac.mkdir(parents=True, exist_ok=True)
        sentinel = '{"existing": true}'
        (sac / "pending_patch.json").write_text(sentinel, encoding="utf-8")

        result = AgentLoop(tmp_path).run("fix calculator bug", max_steps=3)

        assert result.stopped_reason == "approval_required"
        assert result.state.status == "waiting_for_user"
        # Existing file must not be overwritten
        assert (sac / "pending_patch.json").read_text(encoding="utf-8") == sentinel

    def test_patch_proposal_failure_does_not_modify_files(self, tmp_path):
        """When the target file is missing, proposal fails closed without touching files."""
        # No calculator.py → PatchValidator raises, no files written
        result = AgentLoop(tmp_path).run("fix calculator bug", max_steps=3)
        assert not (tmp_path / ".sac" / "pending_patch.json").exists()
        assert result.state.last_error is not None

    def test_existing_orchestrator_edit_flow_unaffected(self, tmp_path):
        """AgentOrchestrator.edit() still works independently of the loop."""
        calc = _setup_calculator(tmp_path)
        original = calc.read_text(encoding="utf-8")
        edit_result = AgentOrchestrator(tmp_path).edit("fix calculator bug")
        assert edit_result.pending_patch_path.exists()
        assert calc.read_text(encoding="utf-8") == original

    def test_journal_records_patch_proposed_event(self, tmp_path):
        _setup_calculator(tmp_path)
        from safecode.state.journal import AgentJournalStore

        result = AgentLoop(tmp_path).run("fix calculator bug", max_steps=3)
        events = AgentJournalStore(tmp_path).read(result.state.session_id)
        types = [e.type for e in events]
        assert "patch_proposed" in types

    def test_cli_agent_run_patch_approval_output(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _setup_calculator(tmp_path)
        result = runner.invoke(app, ["agent", "run", "fix calculator bug", "--max-steps", "3"])
        assert result.exit_code == 0
        output = result.stdout
        assert "approval_required" in output.lower() or "Approval Required" in output
        assert "pending_patch" in output.lower() or "pending" in output.lower()


class TestAgentLoopPatchReadOnlyUnaffected:
    """Read-only agent run behavior from test_agent_session.py must not break."""

    def test_read_intent_still_returned_for_non_write_goal(self, tmp_path):
        from safecode.llm.mock import MockLLMClient

        client = MockLLMClient()
        result = client.choose_tool("fix one bug", {})
        assert result.intent.type == "read"

    def test_run_advances_read_only_path_unchanged(self, tmp_path):
        result = AgentLoop(tmp_path).run("finish the plan", max_steps=5)
        assert result.stopped_reason == "completed"
        assert result.state.status == "completed"
