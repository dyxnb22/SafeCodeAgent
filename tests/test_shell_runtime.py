"""Focused tests for the unified conversational shell runtime."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from safecode.agent.loop import AgentRunResult
from safecode.agent.loop import AgentLoop
from safecode.agent.schemas import AgentNativeToolCallResponse, AgentPlanResponse
from safecode.agent.session import AgentSessionState
from safecode.agent.session import AgentSessionStore
from safecode.patch.models import PatchProposal
from safecode.shell.approvals import adopt_legacy_pending_patch
from safecode.shell.approvals import reject_pending
from safecode.shell.approvals import approve_pending_command
from safecode.shell.memory import render_context_ledger
from safecode.shell.rendering import resume_hint_text, welcome_text
from safecode.shell.session import ShellSessionManifest
from safecode.shell.session import ShellSessionManager
from safecode.utils.time import utc_now_iso


class _CompletedLoop:
    captured_session_ids: list[str | None] = []

    def __init__(self, project_root, **kwargs):
        self.session_id = kwargs.get("session_id")
        self.captured_session_ids.append(self.session_id)

    def run(self, goal, max_steps=8, *, on_step=None, conversation=None):
        state = AgentSessionState(
            session_id=self.session_id or "missing",
            goal=goal or "",
            status="completed",
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        return AgentRunResult(state=state, steps=[], stopped_reason="completed")


def test_shell_auto_resumes_latest_manifest(tmp_path, monkeypatch):
    from safecode.cli import app

    monkeypatch.chdir(tmp_path)
    _CompletedLoop.captured_session_ids.clear()
    runner = CliRunner()
    with patch("safecode.shell.runtime.AgentLoop", _CompletedLoop):
        assert runner.invoke(app, ["shell", "--non-tty"], input="first\n").exit_code == 0
        first = ShellSessionManager(tmp_path / ".sac").latest_id()
        assert runner.invoke(app, ["shell", "--non-tty"], input="second\n").exit_code == 0

    assert first is not None
    assert _CompletedLoop.captured_session_ids == [first, first]


def test_shell_explicit_session_is_shared_with_agent(tmp_path, monkeypatch):
    from safecode.cli import app

    monkeypatch.chdir(tmp_path)
    manifest = ShellSessionManager(tmp_path / ".sac").create()
    _CompletedLoop.captured_session_ids.clear()
    with patch("safecode.shell.runtime.AgentLoop", _CompletedLoop):
        result = CliRunner().invoke(
            app,
            ["shell", "--session", manifest.session_id, "--non-tty"],
            input="inspect this\n",
        )
    assert result.exit_code == 0
    assert _CompletedLoop.captured_session_ids == [manifest.session_id]
    saved = ShellSessionManager(tmp_path / ".sac").load(manifest.session_id)
    assert saved is not None and saved.agent_session_id == manifest.session_id


def test_reject_pending_removes_proposal_without_project_mutation(tmp_path):
    sac_dir = tmp_path / ".sac"
    sac_dir.mkdir()
    pending = sac_dir / "pending_patch.json"
    pending.write_text("{}", encoding="utf-8")
    source = tmp_path / "source.py"
    source.write_text("before\n", encoding="utf-8")

    message = reject_pending(tmp_path)

    assert not pending.exists()
    assert source.read_text(encoding="utf-8") == "before\n"
    assert "No project files were modified" in message


def test_memory_why_explains_injection_policy(tmp_path):
    text = render_context_ledger(tmp_path)
    assert "Memory Context Ledger" in text
    assert "approved facts" in text
    assert "requires explicit approval" in text


def test_keyboard_interrupt_preserves_manifest(tmp_path, monkeypatch):
    from safecode.cli import app

    class _InterruptedLoop(_CompletedLoop):
        def __init__(self, project_root, **kwargs):
            super().__init__(project_root, **kwargs)
            AgentSessionStore(project_root, session_id=self.session_id).start("work", session_id=self.session_id)

        def run(self, goal, max_steps=8, *, on_step=None, conversation=None):
            raise KeyboardInterrupt

    monkeypatch.chdir(tmp_path)
    with patch("safecode.shell.runtime.AgentLoop", _InterruptedLoop):
        result = CliRunner().invoke(app, ["shell", "--non-tty"], input="work\n")

    assert result.exit_code == 130
    manager = ShellSessionManager(tmp_path / ".sac")
    manifest = manager.load(manager.latest_id())
    assert manifest is not None
    assert manifest.interrupted is True
    assert manifest.status == "interrupted"
    agent_state = AgentSessionStore(tmp_path, session_id=manifest.session_id).load()
    assert agent_state is not None
    assert agent_state.status == "interrupted"
    assert agent_state.last_error == "Interrupted by user."


def test_provider_initialization_error_is_structured(tmp_path, monkeypatch):
    from safecode.cli import app

    class _BrokenLoop:
        def __init__(self, project_root, **kwargs):
            raise RuntimeError("credential missing")

    monkeypatch.chdir(tmp_path)
    with patch("safecode.shell.runtime.AgentLoop", _BrokenLoop):
        result = CliRunner().invoke(
            app,
            ["shell", "--non-tty", "--json"],
            input="inspect project\n",
        )

    assert result.exit_code == 1
    assert '"status": "error"' in result.output
    assert "Traceback" not in result.output


def test_agent_state_is_isolated_per_shell_session(tmp_path):
    first = AgentSessionStore(tmp_path, session_id="session-a")
    second = AgentSessionStore(tmp_path, session_id="session-b")

    first.start("first goal")
    second.start("second goal")

    assert first.load().goal == "first goal"
    assert second.load().goal == "second goal"
    assert first.path != second.path
    assert not (tmp_path / ".sac" / "session.json").exists()


def test_shell_session_management_commands(tmp_path, monkeypatch):
    from safecode.cli import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["shell", "--non-tty"],
        input="/rename First session\n/new\n/rename Second session\n/sessions\n/exit\n",
    )

    assert result.exit_code == 0
    assert "First session" in result.output
    assert "Second session" in result.output
    assert len(ShellSessionManager(tmp_path / ".sac").list()) == 2


def test_root_new_option_creates_distinct_sessions(tmp_path, monkeypatch):
    from safecode.cli import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(app, ["--new"], input="/exit\n").exit_code == 0
    assert runner.invoke(app, ["--new"], input="/exit\n").exit_code == 0
    assert len(ShellSessionManager(tmp_path / ".sac").list()) == 2


def test_normal_mode_command_waits_for_inline_approval(tmp_path):
    class _CommandClient:
        def plan(self, goal, context):
            return AgentPlanResponse(goal=goal, steps=["run command"])

        def choose_tool_native(self, goal, context, tool_specs, *, step=0, conversation_history=None):
            return [AgentNativeToolCallResponse(
                tool_name="run_command",
                input={"command": "echo approved"},
                call_id="cmd-1",
            )]

    loop = AgentLoop(tmp_path, llm_client=_CommandClient(), session_id="command-session")
    result = loop.run("run a safe command", max_steps=1)

    assert result.stopped_reason == "approval_required"
    assert result.state.pending_action["type"] == "command"
    assert "approved" in approve_pending_command(
        tmp_path,
        result.state.pending_action,
        session_id="command-session",
    )
    saved = AgentSessionStore(tmp_path, session_id="command-session").load()
    assert saved is not None and saved.pending_action is None


def test_legacy_pending_patch_is_adopted_by_current_session(tmp_path):
    sac_dir = tmp_path / ".sac"
    sac_dir.mkdir()
    proposal = PatchProposal(
        id="legacy-patch",
        task="review this",
        blocks=[],
        created_at="2026-06-18T00:00:00Z",
        model="mock",
    )
    legacy_path = sac_dir / "pending_patch.json"
    legacy_path.write_text(proposal.model_dump_json(), encoding="utf-8")

    assert adopt_legacy_pending_patch(tmp_path, session_id="shell-session") is True

    scoped_path = sac_dir / "sessions" / "shell-session" / "pending_patch.json"
    assert scoped_path.exists()
    assert not legacy_path.exists()
    state = AgentSessionStore(tmp_path, session_id="shell-session").load()
    assert state is not None
    assert state.status == "waiting_for_approval"
    assert state.pending_action is not None
    assert state.pending_action["reason"] == "migrated_legacy_pending_patch"


def test_shell_welcome_and_resume_hint_are_compact():
    manifest = ShellSessionManifest(
        session_id="abcdef123456",
        title="Fix parser",
        mode="plan",
        status="interrupted",
        last_response="Read parser.py and found the next safe step.",
    )

    welcome = welcome_text(manifest, resumed=True, provider="deepseek", model="deepseek-v4-flash")
    hint = resume_hint_text(manifest)

    assert "SafeCode" in welcome
    assert "provider=deepseek" in welcome
    assert "Last response: Read parser.py" in hint
    assert "/continue" in hint
