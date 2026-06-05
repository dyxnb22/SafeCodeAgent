"""Tests for v4.11.2 sac agent run CLI extensions.

Verifies:
- Default max-steps is 8.
- --auto-approve-read-only does not approve edit/apply/run/fix/commit/rollback.
- Non-TTY refusal for approval-required steps when kind is mutating.
- JSON envelope includes last_typed_result without breaking existing fields.
- --no-validate logs a RuntimeWarning.

All surfaces under test are EXPERIMENTAL.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.agent.step_model import APPROVAL_REQUIRED_KINDS, TypedAgentStepResult


runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke_agent_run(tmp_path: Path, args: list[str], input_text: str = "") -> object:
    import os
    import subprocess

    runner_ = CliRunner(mix_stderr=False)
    return runner_.invoke(app, ["agent", "run"] + args)


# ---------------------------------------------------------------------------
# max-steps default is 8
# ---------------------------------------------------------------------------


class TestMaxStepsDefault:
    def test_max_steps_default_is_8(self, tmp_path, monkeypatch):
        """Default --max-steps must be 8."""
        from typer.testing import CliRunner as TR
        from safecode.cli import app

        monkeypatch.chdir(tmp_path)
        result = TR().invoke(app, ["agent", "run", "--help"])
        assert result.exit_code == 0
        assert "8" in result.output

    def test_max_steps_accepts_custom_value(self, tmp_path, monkeypatch):
        """--max-steps N is accepted without error."""
        from typer.testing import CliRunner as TR
        monkeypatch.chdir(tmp_path)
        result = TR().invoke(app, ["agent", "run", "--help"])
        assert "--max-steps" in result.output

    def test_agent_run_runs_up_to_8_steps_by_default(self, tmp_path, monkeypatch):
        """AgentLoop.run is called with max_steps=8 by default."""
        monkeypatch.chdir(tmp_path)

        captured = {}

        class CapturingLoop:
            def __init__(self, project_root, llm_client=None):
                self.project_root = project_root

            def run(self, goal, max_steps=8, *, on_step=None):
                captured["max_steps"] = max_steps
                from safecode.agent.loop import AgentRunResult
                from safecode.agent.session import AgentSessionState
                from safecode.utils.time import utc_now_iso
                state = AgentSessionState(
                    session_id="test-sess-001",
                    goal=goal or "",
                    plan=[],
                    current_step=0,
                    status="completed",
                    pending_action=None,
                    last_observation="done",
                    last_error=None,
                    created_at=utc_now_iso(),
                    updated_at=utc_now_iso(),
                )
                return AgentRunResult(state=state, steps=[], stopped_reason="completed")

            @property
            def last_typed_result(self):
                return None

        with patch("safecode.cli_agent.AgentLoop", CapturingLoop):
            result = CliRunner().invoke(app, ["agent", "run", "test goal"])

        assert captured.get("max_steps") == 8

    def test_agent_run_respects_custom_max_steps(self, tmp_path, monkeypatch):
        """--max-steps 3 passes max_steps=3 to AgentLoop.run."""
        monkeypatch.chdir(tmp_path)

        captured = {}

        class CapturingLoop:
            def __init__(self, project_root, llm_client=None):
                self.project_root = project_root

            def run(self, goal, max_steps=8, *, on_step=None):
                captured["max_steps"] = max_steps
                from safecode.agent.loop import AgentRunResult
                from safecode.agent.session import AgentSessionState
                from safecode.utils.time import utc_now_iso
                state = AgentSessionState(
                    session_id="test-sess-002",
                    goal=goal or "",
                    plan=[],
                    current_step=0,
                    status="completed",
                    pending_action=None,
                    last_observation="done",
                    last_error=None,
                    created_at=utc_now_iso(),
                    updated_at=utc_now_iso(),
                )
                return AgentRunResult(state=state, steps=[], stopped_reason="completed")

            @property
            def last_typed_result(self):
                return None

        with patch("safecode.cli_agent.AgentLoop", CapturingLoop):
            CliRunner().invoke(app, ["agent", "run", "--max-steps", "3", "test goal"])

        assert captured.get("max_steps") == 3


# ---------------------------------------------------------------------------
# --auto-approve-read-only safety invariant
# ---------------------------------------------------------------------------


def _make_loop_with_typed_result(kind: str, stopped_reason: str = "approval_required") -> object:
    """Return a mock AgentLoop whose last_typed_result has the given kind."""
    from safecode.agent.loop import AgentRunResult
    from safecode.agent.session import AgentSessionState
    from safecode.utils.time import utc_now_iso

    state = AgentSessionState(
        session_id="test-sess-003",
        goal="test",
        plan=["step 1"],
        current_step=1,
        status="waiting_for_user",
        pending_action={"type": "patch", "route": "patch.propose"},
        last_observation="waiting",
        last_error=None,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    run_result = AgentRunResult(state=state, steps=[], stopped_reason=stopped_reason)
    typed = TypedAgentStepResult(
        step_index=0, kind=kind,
        status="waiting_for_user" if stopped_reason == "approval_required" else "success",
    )

    class FakeLoop:
        def __init__(self, project_root, llm_client=None):
            pass

        def run(self, goal, max_steps=8, *, on_step=None):
            return run_result

        @property
        def last_typed_result(self):
            return typed

    return FakeLoop


class TestAutoApproveReadOnly:
    @pytest.mark.parametrize("kind", list(APPROVAL_REQUIRED_KINDS))
    def test_auto_approve_read_only_refuses_mutating_kind(self, tmp_path, monkeypatch, kind):
        """--auto-approve-read-only must exit 1 when stopped for a mutating kind."""
        monkeypatch.chdir(tmp_path)
        FakeLoop = _make_loop_with_typed_result(kind, stopped_reason="approval_required")
        with patch("safecode.cli_agent.AgentLoop", FakeLoop):
            result = CliRunner().invoke(
                app, ["agent", "run", "--auto-approve-read-only", "test goal"]
            )
        assert result.exit_code == 1
        assert kind in result.output or "auto-approve" in result.output.lower()

    def test_auto_approve_read_only_json_error_on_mutating(self, tmp_path, monkeypatch):
        """--auto-approve-read-only with --json produces error envelope for mutating kind."""
        monkeypatch.chdir(tmp_path)
        FakeLoop = _make_loop_with_typed_result("edit", stopped_reason="approval_required")
        with patch("safecode.cli_agent.AgentLoop", FakeLoop):
            result = CliRunner().invoke(
                app, ["agent", "run", "--auto-approve-read-only", "--json", "test goal"]
            )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"

    def test_auto_approve_read_only_ok_when_completed(self, tmp_path, monkeypatch):
        """--auto-approve-read-only exits 0 when run completes without approval_required."""
        monkeypatch.chdir(tmp_path)
        FakeLoop = _make_loop_with_typed_result("ask", stopped_reason="completed")
        with patch("safecode.cli_agent.AgentLoop", FakeLoop):
            result = CliRunner().invoke(
                app, ["agent", "run", "--auto-approve-read-only", "test goal"]
            )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Non-TTY fail-closed
# ---------------------------------------------------------------------------


class TestNonTTYRefusal:
    @pytest.mark.parametrize("kind", list(APPROVAL_REQUIRED_KINDS))
    def test_non_tty_refuses_mutating_approval(self, tmp_path, monkeypatch, kind):
        """In non-TTY mode, approval required for mutating kinds must exit 1."""
        monkeypatch.chdir(tmp_path)
        FakeLoop = _make_loop_with_typed_result(kind, stopped_reason="approval_required")
        with patch("safecode.cli_agent.AgentLoop", FakeLoop):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = False
                result = CliRunner(mix_stderr=False).invoke(
                    app, ["agent", "run", "test goal"]
                )
        assert result.exit_code == 1

    def test_non_tty_ok_when_completed(self, tmp_path, monkeypatch):
        """Non-TTY exits 0 when run completes normally."""
        monkeypatch.chdir(tmp_path)
        FakeLoop = _make_loop_with_typed_result("ask", stopped_reason="completed")
        with patch("safecode.cli_agent.AgentLoop", FakeLoop):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = False
                result = CliRunner(mix_stderr=False).invoke(
                    app, ["agent", "run", "test goal"]
                )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# JSON envelope includes last_typed_result
# ---------------------------------------------------------------------------


class TestJsonEnvelope:
    def test_json_envelope_includes_standard_fields(self, tmp_path, monkeypatch):
        """--json output must include session_id, stopped_reason, steps_count, status."""
        monkeypatch.chdir(tmp_path)
        FakeLoop = _make_loop_with_typed_result("ask", stopped_reason="completed")
        with patch("safecode.cli_agent.AgentLoop", FakeLoop):
            result = CliRunner().invoke(app, ["agent", "run", "--json", "test goal"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        data = payload.get("data", payload)
        assert "session_id" in data
        assert "stopped_reason" in data
        assert "steps_count" in data
        assert "status" in data

    def test_json_envelope_includes_last_typed_result(self, tmp_path, monkeypatch):
        """--json output must include last_typed_result when available."""
        monkeypatch.chdir(tmp_path)
        FakeLoop = _make_loop_with_typed_result("ask", stopped_reason="completed")
        with patch("safecode.cli_agent.AgentLoop", FakeLoop):
            result = CliRunner().invoke(app, ["agent", "run", "--json", "test goal"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        data = payload.get("data", payload)
        assert "last_typed_result" in data
        ltr = data["last_typed_result"]
        assert ltr["kind"] == "ask"

    def test_json_envelope_backward_compat_fields_present(self, tmp_path, monkeypatch):
        """Existing JSON fields must remain present alongside new ones."""
        monkeypatch.chdir(tmp_path)
        FakeLoop = _make_loop_with_typed_result("ask", stopped_reason="completed")
        with patch("safecode.cli_agent.AgentLoop", FakeLoop):
            result = CliRunner().invoke(app, ["agent", "run", "--json", "test"])
        payload = json.loads(result.output)
        # The envelope must have command, status at the top level or inside data
        assert "status" in payload or "status" in payload.get("data", {})


# ---------------------------------------------------------------------------
# --no-validate warning
# ---------------------------------------------------------------------------


class TestNoValidate:
    def test_no_validate_logs_runtime_warning(self, tmp_path, monkeypatch):
        """--no-validate must emit a RuntimeWarning."""
        monkeypatch.chdir(tmp_path)
        FakeLoop = _make_loop_with_typed_result("ask", stopped_reason="completed")
        with patch("safecode.cli_agent.AgentLoop", FakeLoop):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                CliRunner().invoke(app, ["agent", "run", "--no-validate", "test"])
        warning_messages = [str(w.message) for w in caught if issubclass(w.category, RuntimeWarning)]
        assert any("no-validate" in m.lower() or "validation" in m.lower() for m in warning_messages)


# ---------------------------------------------------------------------------
# Help text includes new flags
# ---------------------------------------------------------------------------


class TestHelpText:
    def test_agent_run_help_shows_auto_approve_flag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["agent", "run", "--help"])
        assert result.exit_code == 0
        # May be truncated in narrow terminals; check prefix
        assert "--auto-approve-read-on" in result.output

    def test_agent_run_help_shows_no_validate_flag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["agent", "run", "--help"])
        assert result.exit_code == 0
        assert "--no-validate" in result.output

    def test_agent_run_help_shows_experimental(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["agent", "run", "--help"])
        assert result.exit_code == 0
        assert "EXPERIMENTAL" in result.output.upper() or "experimental" in result.output.lower()
