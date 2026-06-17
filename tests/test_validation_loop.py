"""Tests for v4.11.3 agent validation loop."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from safecode.agent.loop import AgentLoop
from safecode.agent.validation import ValidationLoop
from safecode.cli import app
from safecode.project.profile import ProfileCommand, ProjectProfile, save_profile
from safecode.shell.risk import RiskLevel, ShellRisk
from safecode.shell.runner import ShellRunResult
from safecode.state.journal import AgentJournalStore
from safecode.task.store import TaskStore


def _risk(command: str) -> ShellRisk:
    return ShellRisk(level=RiskLevel.LOW, reasons=("test",), tokens=command.split())


def _shell_result(command: str, exit_code: int, stdout: str = "", stderr: str = "") -> ShellRunResult:
    return ShellRunResult(
        command=command,
        risk=_risk(command),
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=1,
        executed=True,
    )


class FakeShellRunner:
    def __init__(self, results: list[ShellRunResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, bool]] = []

    def run(self, command: str, approved: bool = False, timeout_seconds: int | None = None) -> ShellRunResult:
        self.calls.append((command, approved))
        if not self.results:
            return _shell_result(command, 0, stdout="ok")
        return self.results.pop(0)


class FakeOrchestrator:
    def __init__(self) -> None:
        self.edit_calls: list[str] = []
        self.apply_called = False

    def edit(self, task: str):
        self.edit_calls.append(task)
        return SimpleNamespace(proposal=SimpleNamespace(id="repair-patch-1"))

    def apply(self, *args, **kwargs):  # pragma: no cover - should never be reached
        self.apply_called = True
        raise AssertionError("validation repair must not auto-apply")


def _save_profile(
    root: Path,
    *,
    test: tuple[str, ...] | None = ("pytest", "-q"),
    lint: tuple[str, ...] | None = None,
    typecheck: tuple[str, ...] | None = None,
    build: tuple[str, ...] | None = None,
) -> None:
    def cmd(argv: tuple[str, ...] | None) -> ProfileCommand | None:
        if argv is None:
            return None
        return ProfileCommand(command=argv, stack="python", source="user", missing_dependency=False)

    save_profile(
        root,
        ProjectProfile(
            test=cmd(test),
            lint=cmd(lint),
            typecheck=cmd(typecheck),
            build=cmd(build),
            user_overrides=frozenset(),
        ),
    )


class TestValidationLoop:
    def test_validation_success(self, tmp_path: Path) -> None:
        _save_profile(tmp_path)
        shell = FakeShellRunner([_shell_result("pytest -q", 0, stdout="passed")])
        result = ValidationLoop(tmp_path, shell_runner=shell).run_after_apply(
            session_id="session-0001",
            step_index=1,
            goal="goal",
        )
        assert result.status == "success"
        assert [r.suite for r in result.suite_results] == ["test"]
        assert shell.calls == [("pytest -q", True)]

    def test_validation_failure_feeds_next_fix_step(self, tmp_path: Path) -> None:
        _save_profile(tmp_path)
        shell = FakeShellRunner([_shell_result("pytest -q", 1, stderr="SECRET=123\nfailed")])
        orchestrator = FakeOrchestrator()
        result = ValidationLoop(tmp_path, shell_runner=shell, orchestrator=orchestrator).run_after_apply(
            session_id="session-0002",
            step_index=2,
            goal="fix tests",
        )
        assert result.status == "repair_proposed"
        assert result.synthetic_fix_step is not None
        assert result.synthetic_fix_step.kind == "fix"
        assert orchestrator.edit_calls
        assert "failed" in orchestrator.edit_calls[0]
        assert "SECRET=123" not in (result.failure_tail or "")

    def test_validation_repair_prompt_includes_pyright_diagnostics(self, tmp_path: Path) -> None:
        _save_profile(tmp_path)
        shell = FakeShellRunner([_shell_result("pytest -q", 1, stderr="TypeError: bad")])
        orchestrator = FakeOrchestrator()
        with patch("safecode.index.lsp_bridge.PyrightBridge.get_diagnostics", return_value=[
            {
                "file": "src/foo.py",
                "line": 4,
                "column": 2,
                "severity": "error",
                "rule": "reportArgumentType",
                "message": "Argument type mismatch",
            }
        ]):
            ValidationLoop(tmp_path, shell_runner=shell, orchestrator=orchestrator).run_after_apply(
                session_id="session-diag-repair",
                step_index=2,
                goal="fix types",
            )
        assert orchestrator.edit_calls
        assert "Type diagnostics" in orchestrator.edit_calls[0]
        assert "src/foo.py:4:2" in orchestrator.edit_calls[0]

    def test_loop_no_progress_stop_on_unchanged_failure_tail_hash(self, tmp_path: Path) -> None:
        _save_profile(tmp_path)
        shell = FakeShellRunner([_shell_result("pytest -q", 1, stderr="same failure")])
        first = ValidationLoop(tmp_path, shell_runner=shell, orchestrator=FakeOrchestrator()).run_after_apply(
            session_id="session-0003",
            step_index=1,
            goal="goal",
        )
        shell2 = FakeShellRunner([_shell_result("pytest -q", 1, stderr="same failure")])
        second = ValidationLoop(tmp_path, shell_runner=shell2, orchestrator=FakeOrchestrator()).run_after_apply(
            session_id="session-0003",
            step_index=2,
            goal="goal",
            previous_failure_tail_hash=first.failure_tail_hash,
            repair_iterations=1,
        )
        assert second.status == "loop_no_progress"
        assert second.stop_reason == "loop_no_progress"

    def test_max_repair_iterations(self, tmp_path: Path) -> None:
        _save_profile(tmp_path)
        shell = FakeShellRunner([_shell_result("pytest -q", 1, stderr="failed")])
        result = ValidationLoop(tmp_path, shell_runner=shell, max_repair_iterations=2).run_after_apply(
            session_id="session-0004",
            step_index=1,
            goal="goal",
            repair_iterations=2,
        )
        assert result.status == "max_repair_iterations"

    def test_missing_profile_suite_skips_with_clear_note(self, tmp_path: Path) -> None:
        result = ValidationLoop(tmp_path, shell_runner=FakeShellRunner([])).run_after_apply(
            session_id="session-0005",
            step_index=1,
            goal="goal",
        )
        assert result.status == "skipped"
        assert result.stop_reason == "missing_profile"
        assert "sac profile detect" in result.notes[0]

    def test_lint_typecheck_build_ordering_when_configured(self, tmp_path: Path) -> None:
        _save_profile(
            tmp_path,
            lint=("ruff", "check", "."),
            typecheck=("mypy", "."),
            build=("python", "-m", "build"),
        )
        shell = FakeShellRunner([
            _shell_result("pytest -q", 0),
            _shell_result("ruff check .", 0),
            _shell_result("mypy .", 0),
            _shell_result("python -m build", 0),
        ])
        result = ValidationLoop(tmp_path, shell_runner=shell).run_after_apply(
            session_id="session-0006",
            step_index=1,
            goal="goal",
        )
        assert [r.suite for r in result.suite_results] == ["test", "lint", "typecheck", "build"]

    def test_repair_proposal_never_auto_applies(self, tmp_path: Path) -> None:
        _save_profile(tmp_path)
        orchestrator = FakeOrchestrator()
        ValidationLoop(
            tmp_path,
            shell_runner=FakeShellRunner([_shell_result("pytest -q", 1, stderr="failed")]),
            orchestrator=orchestrator,
        ).run_after_apply(session_id="session-0007", step_index=1, goal="goal")
        assert orchestrator.edit_calls
        assert orchestrator.apply_called is False

    def test_journal_receives_typed_validation_and_repair_result(self, tmp_path: Path) -> None:
        _save_profile(tmp_path)
        ValidationLoop(
            tmp_path,
            shell_runner=FakeShellRunner([_shell_result("pytest -q", 1, stderr="failed")]),
            orchestrator=FakeOrchestrator(),
        ).run_after_apply(session_id="session-0008", step_index=1, goal="goal")
        events = AgentJournalStore(tmp_path).read("session-0008")
        typed = [event.payload for event in events if event.type == "typed_result"]
        kinds = [payload["typed_result"]["kind"] for payload in typed]
        assert "run" in kinds
        assert "fix" in kinds

    def test_task_iteration_records_validation_and_repair(self, tmp_path: Path) -> None:
        _save_profile(tmp_path)
        task = TaskStore(tmp_path).create("goal")
        ValidationLoop(
            tmp_path,
            shell_runner=FakeShellRunner([_shell_result("pytest -q", 1, stderr="failed")]),
            orchestrator=FakeOrchestrator(),
        ).run_after_apply(session_id="session-0009", step_index=1, goal="goal")
        saved = TaskStore(tmp_path).load(task.task_id)
        assert saved is not None
        assert [iteration.event for iteration in saved.iterations] == ["validation", "fix"]


class TestAgentLoopValidationIntegration:
    def test_apply_kind_invokes_validation(self, tmp_path: Path) -> None:
        loop = AgentLoop(tmp_path)
        state = loop.store.start("goal", plan=["apply"])
        loop._classify_and_record(
            step_index=1,
            pending_action={"type": "mcp", "route": "mcp.execute_approved_write"},
            observation="applied",
            stopped_for_approval=False,
            session_id=state.session_id,
        )
        with patch("safecode.agent.loop.ValidationLoop") as MockValidation:
            MockValidation.return_value.run_after_apply.return_value = SimpleNamespace(
                status="success",
                stop_reason="validation_success",
                notes=(),
            )
            assert loop._should_validate_after_step() is True
            loop._run_validation_after_apply(state)
        assert MockValidation.return_value.run_after_apply.called

    def test_no_validate_disables_validation_and_cli_warning(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        captured: dict[str, bool] = {}

        class FakeLoop:
            def __init__(self, project_root, llm_client=None):
                self.no_validate = False

            def run(self, goal, max_steps=8, *, on_step=None):
                captured["no_validate"] = self.no_validate
                from safecode.agent.loop import AgentRunResult
                from safecode.agent.session import AgentSessionState
                from safecode.utils.time import utc_now_iso
                state = AgentSessionState(
                    session_id="session-0010",
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

        with patch("safecode.cli_agent.AgentLoop", FakeLoop):
            result = CliRunner().invoke(app, ["agent", "run", "--no-validate", "goal"])
        assert result.exit_code == 0
        assert captured["no_validate"] is True
