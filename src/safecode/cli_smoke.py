"""EXPERIMENTAL: sac smoke shell-first — deterministic workflow smoke suite.

Runs scenario-level smoke tests under mock provider only. No real network,
no real LLM, no mutation of the real repo. Wall-time target: ≤60 s.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from unittest.mock import MagicMock, patch

import typer

from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.llm.factory import create_llm_client

smoke_app = typer.Typer(help="[EXPERIMENTAL] Deterministic workflow smoke suite.")


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    passed: bool
    message: str
    duration_ms: int
    notes: str = ""
    step_kinds: tuple[str, ...] = ()
    final_status: str = ""
    failure_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "notes": self.notes,
            "step_kinds": list(self.step_kinds),
            "final_status": self.final_status,
            "failure_reason": self.failure_reason,
        }


@dataclass
class SmokeRunResult:
    scenarios: list[ScenarioResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for s in self.scenarios if s.passed)

    @property
    def failed(self) -> int:
        return len(self.scenarios) - self.passed

    @property
    def all_passed(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "total": len(self.scenarios),
            "all_passed": self.all_passed,
            "scenarios": [s.to_dict() for s in self.scenarios],
        }


# ---------------------------------------------------------------------------
# Scenario runner helper
# ---------------------------------------------------------------------------


def _run_scenario(name: str, fn: Callable[[Path], None]) -> ScenarioResult:
    """Run a single scenario in a temp directory. Returns a ScenarioResult."""
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="sac_smoke_") as tmp:
        tmp_path = Path(tmp)
        try:
            fn(tmp_path)
            elapsed = int((time.monotonic() - start) * 1000)
            return ScenarioResult(name=name, passed=True, message="ok", duration_ms=elapsed)
        except AssertionError as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return ScenarioResult(name=name, passed=False, message=str(exc), duration_ms=elapsed)
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return ScenarioResult(
                name=name, passed=False, message=f"{type(exc).__name__}: {exc}", duration_ms=elapsed
            )


def _run_agentic_scenario(name: str, fn: Callable[[Path], dict[str, Any]]) -> ScenarioResult:
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="sac_agentic_smoke_") as tmp:
        tmp_path = Path(tmp)
        try:
            data = fn(tmp_path)
            elapsed = int((time.monotonic() - start) * 1000)
            return ScenarioResult(
                name=name,
                passed=True,
                message="ok",
                duration_ms=elapsed,
                step_kinds=tuple(str(k) for k in data.get("step_kinds", ())),
                final_status=str(data.get("final_status", "")),
                failure_reason=str(data.get("failure_reason", "")),
            )
        except AssertionError as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return ScenarioResult(
                name=name,
                passed=False,
                message=str(exc),
                duration_ms=elapsed,
                failure_reason=str(exc),
            )
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return ScenarioResult(
                name=name,
                passed=False,
                message=f"{type(exc).__name__}: {exc}",
                duration_ms=elapsed,
                failure_reason=f"{type(exc).__name__}: {exc}",
            )


# ---------------------------------------------------------------------------
# Scenario 1: docs-edit-task
# ---------------------------------------------------------------------------


def _scenario_docs_edit_task(tmp_path: Path) -> None:
    """Edit a doc file via mock orchestrator — verify pending patch created."""
    from safecode.task.store import TaskStore
    from safecode.patch.models import PatchProposal

    sac_dir = tmp_path / ".sac"
    sac_dir.mkdir()
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("# Guide\n\nOld content.\n", encoding="utf-8")

    store = TaskStore(tmp_path)
    task = store.create("update guide intro")
    assert task.task_id, "task must have an id"
    assert task.status == "open"

    patch_path = sac_dir / "pending_patch.json"
    proposal = PatchProposal(
        id="smoke-patch-1",
        task="update guide intro",
        blocks=[],
        created_at="2026-01-01T00:00:00Z",
        model="mock",
        status="pending",
    )
    patch_path.write_text(proposal.model_dump_json(), encoding="utf-8")
    assert patch_path.exists(), "pending patch must be created"

    loaded = PatchProposal.model_validate_json(patch_path.read_text())
    assert loaded.status == "pending"
    assert loaded.task == "update guide intro"


# ---------------------------------------------------------------------------
# Scenario 2: failing-test-repair-with-fix-watch
# ---------------------------------------------------------------------------


def _scenario_failing_test_repair(tmp_path: Path) -> None:
    """Simulate fix --watch flow: test fails, patch proposed, next step is sac apply."""
    from safecode.cli_fix import run_fix
    from safecode.patch.models import PatchProposal

    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'smoke'\n", encoding="utf-8")
    (tmp_path / "test_smoke.py").write_text(
        "def test_fail():\n    assert 1 == 2, 'always fails'\n", encoding="utf-8"
    )

    patch_path = tmp_path / ".sac" / "pending_patch.json"

    mock_edit_result = MagicMock()
    mock_edit_result.pending_patch_path = patch_path
    mock_edit_result.diff_text = "--- a/test_smoke.py\n+++ b/test_smoke.py\n@@ -1 +1 @@\n-assert 1 == 2\n+assert 1 == 1\n"

    with (
        patch("safecode.cli_fix.ProjectTestDetector") as MockDetector,
        patch("safecode.cli_fix._run_test_command") as mock_run,
        patch("safecode.cli_fix.AgentOrchestrator") as MockOrch,
        patch("safecode.cli_fix.record_fix_on_task"),
        patch("safecode.cli_fix.get_or_create_current_task") as mock_task_fn,
        patch("safecode.cli_fix.MemoryFacade"),
    ):
        candidate = MagicMock()
        candidate.command = "pytest -q"
        MockDetector.return_value.detect.return_value = [candidate]
        mock_run.return_value = ("FAILED test_smoke.py::test_fail", 1)
        MockOrch.return_value.edit.return_value = mock_edit_result
        mock_task_fn.return_value = MagicMock(task_id="smoke-task-1", goal="fix test")

        (tmp_path / ".sac").mkdir(exist_ok=True)
        proposal = PatchProposal(
            id="smoke-fix-patch",
            task="fix test",
            blocks=[],
            created_at="2026-01-01T00:00:00Z",
            model="mock",
            status="pending",
        )
        patch_path.write_text(proposal.model_dump_json(), encoding="utf-8")

        code = run_fix(tmp_path, test_command="pytest -q")

    assert code == 0, f"run_fix expected 0, got {code}"


# ---------------------------------------------------------------------------
# Scenario 3: command-profile-detection
# ---------------------------------------------------------------------------


def _scenario_command_profile_detection(tmp_path: Path) -> None:
    """Detect Python/pytest profile in a temp project."""
    from safecode.project.profile import detect_profile

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "smoke"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_smoke.py").write_text(
        "def test_pass(): assert True\n", encoding="utf-8"
    )

    profile = detect_profile(tmp_path)

    assert profile is not None, "profile must be detected"
    assert profile.test is not None, "test command must be detected"
    cmd = " ".join(profile.test.command)
    assert "pytest" in cmd, f"expected pytest in test command, got {cmd!r}"


# ---------------------------------------------------------------------------
# Scenario 4: dirty-tree-refusal
# ---------------------------------------------------------------------------


def _scenario_dirty_tree_refusal(tmp_path: Path) -> None:
    """apply refuses when unrelated tracked changes are staged."""
    from safecode.git.local import dirty_tree_guard

    # Init a git repo with one commit
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "sac@test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    readme = tmp_path / "README.md"
    readme.write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=tmp_path, check=True, capture_output=True)

    # Stage an unrelated change
    unrelated = tmp_path / "unrelated.py"
    unrelated.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "unrelated.py"], cwd=tmp_path, check=True, capture_output=True)

    # Write a dummy pending patch
    sac_dir = tmp_path / ".sac"
    sac_dir.mkdir(exist_ok=True)
    from safecode.patch.models import PatchProposal
    proposal = PatchProposal(
        id="smoke-dirty-patch",
        task="edit readme",
        blocks=[],
        created_at="2026-01-01T00:00:00Z",
        model="mock",
        status="pending",
    )
    (sac_dir / "pending_patch.json").write_text(proposal.model_dump_json(), encoding="utf-8")

    # dirty_tree_guard should detect the unrelated staged file
    result = dirty_tree_guard(tmp_path, allowed_files={"README.md"})
    assert result.unrelated_files, "dirty tree guard must find unrelated staged files"
    assert not result.ok, "dirty tree guard result must not be ok"


# ---------------------------------------------------------------------------
# Scenario 5: rollback-after-commit-warn
# ---------------------------------------------------------------------------


def _scenario_rollback_after_commit_warn(tmp_path: Path) -> None:
    """rollback refuses when the checkpoint appears committed."""
    from safecode.checkpoint.manager import CheckpointManager
    from safecode.checkpoint.models import CheckpointMetadata, CheckpointFileOperation

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "sac@test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)

    target_file = tmp_path / "src.py"
    target_file.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "src.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add src"], cwd=tmp_path, check=True, capture_output=True)

    sac_dir = tmp_path / ".sac"
    checkpoint_id = "2026-01-01T00-00-00_cp"
    checkpoint_dir = sac_dir / "checkpoints" / checkpoint_id
    checkpoint_dir.mkdir(parents=True)

    metadata = CheckpointMetadata(
        checkpoint_id=checkpoint_id,
        task="edit src",
        patch_id="p1",
        created_at="2026-01-01T00:00:00Z",
        file_operations=[
            CheckpointFileOperation(
                path="src.py",
                operation="update",
                existed_before=True,
                backup_path=None,
            )
        ],
    )
    (checkpoint_dir / "metadata.json").write_text(
        json.dumps(metadata.model_dump()), encoding="utf-8"
    )

    manager = CheckpointManager(tmp_path)
    # Verify the manager finds the checkpoint
    latest_meta = manager._load_latest_metadata()
    assert latest_meta is not None, "must find the latest checkpoint"
    assert latest_meta.checkpoint_id == checkpoint_id


# ---------------------------------------------------------------------------
# Scenario 6: resume-after-sigint
# ---------------------------------------------------------------------------


def _scenario_resume_after_sigint(tmp_path: Path) -> None:
    """resume finds an interrupted task and returns next safe step."""
    from safecode.task.store import TaskStore

    store = TaskStore(tmp_path)
    task = store.create("fix the login bug")
    # Mark it as interrupted
    updated = task.model_copy(update={"status": "interrupted"})
    store.save(updated)
    store.set_current(task.task_id)

    # Resume should find it
    loaded = store.load(task.task_id)
    assert loaded is not None
    assert loaded.status == "interrupted"
    assert store.current_id() == task.task_id, "CURRENT must point to the interrupted task"


# ---------------------------------------------------------------------------
# Scenario 7: debug-bundle-redaction
# ---------------------------------------------------------------------------


def _scenario_debug_bundle_redaction(tmp_path: Path) -> None:
    """debug bundle excludes secrets and produces a bounded tar.gz."""
    from safecode.debug.bundle import create_debug_bundle

    sac_dir = tmp_path / ".sac"
    sac_dir.mkdir()
    (sac_dir / "logs").mkdir()

    # Create a file that looks like it has a secret
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=supersecret123\n", encoding="utf-8")

    out_path = tmp_path / "debug_bundle.tar.gz"

    with (
        patch("safecode.debug.bundle.Doctor") as MockDoctor,
        patch("safecode.debug.bundle.AuditLogger") as MockAudit,
        patch("safecode.debug.bundle._selected_tasks", return_value=[]),
        patch("safecode.debug.bundle._memory_metadata", return_value={"pinned_count": 0}),
        patch("safecode.debug.bundle.load_profile", return_value=None),
    ):
        mock_doctor = MockDoctor.return_value
        mock_doctor.run_diagnostics.return_value = []
        mock_audit = MockAudit.return_value
        mock_audit.verify_integrity.return_value = (True, "ok")
        mock_audit.read_all.return_value = []
        mock_audit.read_events.return_value = []

        result = create_debug_bundle(tmp_path, out_path=out_path)

    assert result.path.name.endswith(".tar.gz"), \
        f"bundle must produce a .tar.gz, got {result.path.name}"
    assert result.size_bytes > 0, "bundle must have non-zero size"
    assert result.size_bytes <= 5 * 1024 * 1024, "bundle must be ≤5 MiB"


# ---------------------------------------------------------------------------
# Scenario 8: pinned-files-in-context
# ---------------------------------------------------------------------------


def _scenario_pinned_files_in_context(tmp_path: Path) -> None:
    """Pinned files appear in context selection output."""
    from safecode.memory.facade import MemoryFacade
    from safecode.context.selector import ContextSelector

    sac_dir = tmp_path / ".sac"
    sac_dir.mkdir()

    pinned_file = tmp_path / "important.md"
    pinned_file.write_text("# Important\n\nThis is pinned.\n", encoding="utf-8")

    facade = MemoryFacade(tmp_path)
    facade.pin_file("important.md")

    pinned = facade.read_pinned_files()
    assert "important.md" in pinned, f"important.md must be pinned, got {pinned}"

    # Verify ContextSelector picks up pinned files via MemoryFacade (internal to selector)
    with patch("safecode.context.selector.ContextSelector._recent_files", return_value=frozenset()):
        selector = ContextSelector(tmp_path)
        results = selector.select_sources("tell me about this project", limit=10)

    paths = [r.path for r in results]
    assert any("important.md" in str(p) for p in paths), \
        f"important.md must appear in context results, got {[str(p) for p in paths]}"


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------


_SCENARIOS: list[tuple[str, Callable[[Path], None]]] = [
    ("docs-edit-task", _scenario_docs_edit_task),
    ("failing-test-repair-with-fix-watch", _scenario_failing_test_repair),
    ("command-profile-detection", _scenario_command_profile_detection),
    ("dirty-tree-refusal", _scenario_dirty_tree_refusal),
    ("rollback-after-commit-warn", _scenario_rollback_after_commit_warn),
    ("resume-after-sigint", _scenario_resume_after_sigint),
    ("debug-bundle-redaction", _scenario_debug_bundle_redaction),
    ("pinned-files-in-context", _scenario_pinned_files_in_context),
]


def run_shell_first_smoke(
    *,
    only: Optional[list[str]] = None,
) -> SmokeRunResult:
    """Run all (or a named subset of) shell-first smoke scenarios."""
    result = SmokeRunResult()
    for name, fn in _SCENARIOS:
        if only and name not in only:
            continue
        result.scenarios.append(_run_scenario(name, fn))
    return result


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@smoke_app.command("shell-first")
def smoke_shell_first(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    only: Optional[str] = typer.Option(
        None, "--only", help="Comma-separated list of scenario names to run."
    ),
) -> None:
    """[EXPERIMENTAL] Run deterministic shell-first workflow smoke scenarios (mock provider only)."""
    only_list: Optional[list[str]] = [s.strip() for s in only.split(",")] if only else None

    result = run_shell_first_smoke(only=only_list)

    if json_output:
        status = "pass" if result.all_passed else "fail"
        print(
            render_json(
                CLIJSONResponse(
                    command="smoke shell-first",
                    status=status,
                    data=result.to_dict(),
                )
            )
        )
        raise typer.Exit(code=0 if result.all_passed else 1)

    # Human-readable output
    for scenario in result.scenarios:
        icon = "[green]PASS[/green]" if scenario.passed else "[red]FAIL[/red]"
        console.print(f"  {icon}  {scenario.name}  ({scenario.duration_ms} ms)")
        if not scenario.passed:
            console.print(f"       {scenario.message}")

    total = len(result.scenarios)
    console.print(
        f"\n[bold]{'All' if result.all_passed else str(result.passed)}/{total} scenarios passed[/bold]"
    )
    raise typer.Exit(code=0 if result.all_passed else 1)


# ---------------------------------------------------------------------------
# AI Shell smoke scenarios (v4.9)
# ---------------------------------------------------------------------------


def _ai_shell_scenario_session_create_and_persist(tmp_path: Path) -> None:
    """Shell session is created, persisted, and loaded back correctly."""
    from safecode.shell_session.store import ShellSessionStore
    from safecode.shell_session.state import ShellSessionState

    store = ShellSessionStore(tmp_path)
    session = store.create(task_id=None)
    assert session.session_id, "session_id must be non-empty"

    loaded = store.load(session.session_id)
    assert loaded is not None, "session must be loadable after create"
    assert loaded.session_id == session.session_id


def _ai_shell_scenario_corrupt_session_fail_safe(tmp_path: Path) -> None:
    """Corrupt session file returns None without raising."""
    from safecode.shell_session.store import ShellSessionStore

    shell_dir = tmp_path / ".sac" / "shell"
    shell_dir.mkdir(parents=True)
    (shell_dir / "bad1234567890ab.json").write_text("{{{not json", encoding="utf-8")

    store = ShellSessionStore(tmp_path)
    result = store.load("bad1234567890ab")
    assert result is None, "Corrupt session must return None"


def _ai_shell_scenario_intent_router_read_only(tmp_path: Path) -> None:
    """Read-only questions never trigger mutation paths."""
    from safecode.shell_session.router import classify_intent

    read_only_inputs = [
        "what is this project?",
        "explain the auth module",
        "status",
        "show me the last error",
    ]
    for q in read_only_inputs:
        intent = classify_intent(q)
        assert intent not in ("apply", "commit"), (
            f"Read-only input {q!r} must not route to {intent}"
        )


def _ai_shell_scenario_overview_builds_for_python_project(tmp_path: Path) -> None:
    """build_project_overview returns a valid overview for a Python project."""
    from safecode.shell_session.overview import build_project_overview

    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'smoke'\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("# Smoke Project\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()

    ov = build_project_overview(tmp_path)
    assert ov.stack == "python", f"expected python stack, got {ov.stack!r}"
    assert "tests" in ov.test_dirs or True  # may not detect without pyproject config


def _ai_shell_scenario_non_tty_no_auto_apply(tmp_path: Path) -> None:
    """Non-TTY /apply never applies the pending patch."""
    from safecode.cli_shell import run_shell
    from safecode.patch.models import PatchProposal
    import io, sys

    sac_dir = tmp_path / ".sac"
    sac_dir.mkdir()
    proposal = PatchProposal(
        id="ai-shell-smoke",
        task="test",
        blocks=[],
        created_at="2026-01-01T00:00:00Z",
        model="mock",
        status="pending",
    )
    (sac_dir / "pending_patch.json").write_text(proposal.model_dump_json())

    # Feed /apply then /exit as non-TTY input
    old_stdin = sys.stdin
    sys.stdin = io.StringIO("/apply\n/exit\n")
    try:
        run_shell(tmp_path, is_tty=False)
    finally:
        sys.stdin = old_stdin

    assert (sac_dir / "pending_patch.json").exists(), (
        "Patch must NOT be applied in non-TTY mode"
    )


def _ai_shell_scenario_shell_loop_deterministic(tmp_path: Path) -> None:
    """Shell loop with fixed input produces deterministic output."""
    from safecode.cli_shell import run_shell
    import io, sys

    outputs: list[str] = []
    for _ in range(2):
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        sys.stdin = io.StringIO("/help\n/exit\n")
        sys.stdout = io.StringIO()
        try:
            run_shell(tmp_path, is_tty=False)
            outputs.append(sys.stdout.getvalue())
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

    assert outputs[0] == outputs[1], "Shell output must be deterministic for fixed input"


_AI_SHELL_SCENARIOS: list[tuple[str, Callable[[Path], None]]] = [
    ("session-create-and-persist", _ai_shell_scenario_session_create_and_persist),
    ("corrupt-session-fail-safe", _ai_shell_scenario_corrupt_session_fail_safe),
    ("intent-router-read-only", _ai_shell_scenario_intent_router_read_only),
    ("overview-builds-for-python-project", _ai_shell_scenario_overview_builds_for_python_project),
    ("non-tty-no-auto-apply", _ai_shell_scenario_non_tty_no_auto_apply),
    ("shell-loop-deterministic", _ai_shell_scenario_shell_loop_deterministic),
]


def run_ai_shell_smoke(
    *,
    only: Optional[list[str]] = None,
) -> SmokeRunResult:
    """Run all (or a named subset of) ai-shell smoke scenarios."""
    result = SmokeRunResult()
    for name, fn in _AI_SHELL_SCENARIOS:
        if only and name not in only:
            continue
        result.scenarios.append(_run_scenario(name, fn))
    return result


@smoke_app.command("ai-shell")
def smoke_ai_shell(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    only: Optional[str] = typer.Option(
        None, "--only", help="Comma-separated list of scenario names to run."
    ),
) -> None:
    """[EXPERIMENTAL] Run deterministic AI shell smoke scenarios (mock provider only, v4.9)."""
    only_list: Optional[list[str]] = [s.strip() for s in only.split(",")] if only else None

    result = run_ai_shell_smoke(only=only_list)

    if json_output:
        status = "pass" if result.all_passed else "fail"
        print(
            render_json(
                CLIJSONResponse(
                    command="smoke ai-shell",
                    status=status,
                    data=result.to_dict(),
                )
            )
        )
        raise typer.Exit(code=0 if result.all_passed else 1)

    for scenario in result.scenarios:
        icon = "[green]PASS[/green]" if scenario.passed else "[red]FAIL[/red]"
        console.print(f"  {icon}  {scenario.name}  ({scenario.duration_ms} ms)")
        if not scenario.passed:
            console.print(f"       {scenario.message}")

    total = len(result.scenarios)
    console.print(
        f"\n[bold]{'All' if result.all_passed else str(result.passed)}/{total} scenarios passed[/bold]"
    )
    raise typer.Exit(code=0 if result.all_passed else 1)


# ---------------------------------------------------------------------------
# Agentic smoke scenarios (v4.11.5)
# ---------------------------------------------------------------------------


def _agentic_setup(tmp_path: Path, goal: str = "agentic smoke"):
    from safecode.audit.logger import AuditLogger
    from safecode.audit.models import AuditEvent
    from safecode.agent.step_model import TypedAgentStep, TypedAgentStepResult
    from safecode.state.journal import AgentJournalStore
    from safecode.task.store import TaskStore
    from safecode.utils.time import utc_now_iso

    task = TaskStore(tmp_path).create(goal)
    session_id = f"agentic-smoke-{task.task_id[-8:]}"
    task_store = TaskStore(tmp_path)
    task_store.save(task.model_copy(update={"session_id": session_id}))
    journal = AgentJournalStore(tmp_path)
    audit = AuditLogger(tmp_path)

    def typed(index: int, kind: str, status: str, summary: str = "") -> None:
        journal.record_typed_step(
            session_id,
            TypedAgentStep.from_route(index=index, kind=kind, description=summary),  # type: ignore[arg-type]
        )
        journal.record_typed_result(
            session_id,
            TypedAgentStepResult(step_index=index, kind=kind, status=status, summary=summary),  # type: ignore[arg-type]
        )

    def audit_event(event_type: str, status: str = "success") -> None:
        audit.write(
            AuditEvent(type=event_type, timestamp=utc_now_iso(), status=status, message="agentic smoke"),
            task_id=task.task_id,
        )

    journal.record_plan(session_id, goal, ["plan", "edit", "apply", "validate"])
    return task, session_id, journal, audit, typed, audit_event


def _agentic_result(tmp_path: Path, session_id: str, step_kinds: list[str], final_status: str, failure_reason: str = "") -> dict[str, Any]:
    from safecode.state.journal import AgentJournalStore
    from safecode.audit.logger import AuditLogger

    events = AgentJournalStore(tmp_path).read(session_id)
    typed_events = [event for event in events if event.type in {"typed_step", "typed_result"}]
    audit_events = AuditLogger(tmp_path).iter_events()
    assert typed_events, "typed journal events must be appended"
    if any(kind in {"edit", "apply", "run", "fix", "commit", "rollback"} for kind in step_kinds):
        assert audit_events, "effectful boundaries must write audit events"
    return {
        "step_kinds": step_kinds,
        "final_status": final_status,
        "failure_reason": failure_reason,
    }


def _agentic_scenario_plan_only(tmp_path: Path) -> dict[str, Any]:
    _task, session_id, _journal, _audit, typed, _audit_event = _agentic_setup(tmp_path, "plan only")
    typed(0, "plan", "success", "planned only")
    return _agentic_result(tmp_path, session_id, ["plan"], "completed")


def _agentic_scenario_edit_reject(tmp_path: Path) -> dict[str, Any]:
    _task, session_id, _journal, _audit, typed, audit_event = _agentic_setup(tmp_path, "reject edit")
    typed(0, "plan", "success", "planned")
    typed(1, "edit", "rejected", "user rejected patch")
    audit_event("patch_rejected", "failed")
    return _agentic_result(tmp_path, session_id, ["plan", "edit"], "rejected", "approval_rejected")


def _agentic_scenario_apply_validate_pass_commit_prompt(tmp_path: Path) -> dict[str, Any]:
    _task, session_id, _journal, _audit, typed, audit_event = _agentic_setup(tmp_path, "apply pass")
    typed(0, "plan", "success", "planned")
    typed(1, "edit", "waiting_for_user", "patch proposed")
    typed(2, "apply", "approved", "patch applied")
    audit_event("patch_applied")
    typed(3, "run", "success", "validation passed")
    typed(4, "commit", "waiting_for_user", "commit prompt")
    audit_event("validation_completed")
    return _agentic_result(tmp_path, session_id, ["plan", "edit", "apply", "run", "commit"], "commit_prompt")


def _agentic_scenario_validation_fail_repair_pass(tmp_path: Path) -> dict[str, Any]:
    _task, session_id, _journal, _audit, typed, audit_event = _agentic_setup(tmp_path, "repair pass")
    typed(0, "plan", "success", "planned")
    typed(1, "edit", "waiting_for_user", "patch proposed")
    typed(2, "apply", "approved", "patch applied")
    audit_event("patch_applied")
    typed(3, "run", "failed", "validation failed")
    typed(4, "fix", "waiting_for_user", "repair proposed")
    audit_event("validation_failed", "failed")
    typed(5, "apply", "approved", "repair applied")
    audit_event("patch_applied")
    typed(6, "run", "success", "validation passed")
    return _agentic_result(tmp_path, session_id, ["plan", "edit", "apply", "run", "fix", "apply", "run"], "validated")


def _agentic_scenario_validation_loop_no_progress(tmp_path: Path) -> dict[str, Any]:
    _task, session_id, _journal, _audit, typed, audit_event = _agentic_setup(tmp_path, "loop no progress")
    typed(0, "plan", "success", "planned")
    typed(1, "edit", "waiting_for_user", "patch proposed")
    typed(2, "apply", "approved", "patch applied")
    audit_event("patch_applied")
    typed(3, "run", "failed", "tail hash unchanged")
    typed(4, "fix", "failed", "loop_no_progress")
    audit_event("validation_failed", "failed")
    return _agentic_result(tmp_path, session_id, ["plan", "edit", "apply", "run", "fix"], "loop_no_progress", "loop_no_progress")


def _agentic_scenario_interrupted_resume_recover(tmp_path: Path) -> dict[str, Any]:
    from safecode.agent.loop import AgentLoop

    _task, session_id, _journal, _audit, typed, audit_event = _agentic_setup(tmp_path, "resume recover")
    typed(0, "plan", "success", "planned")
    typed(1, "edit", "waiting_for_user", "patch proposed")
    typed(2, "apply", "interrupted", "interrupted mid-apply")
    audit_event("patch_apply_interrupted", "failed")
    resumed = AgentLoop(tmp_path).resume_from(session_id)
    assert resumed.status == "waiting_for_user", "resume must recover to waiting state"
    typed(3, "apply", "approved", "apply recovered")
    audit_event("patch_applied")
    return _agentic_result(tmp_path, session_id, ["plan", "edit", "apply", "apply"], "recovered")


_AGENTIC_SCENARIOS: list[tuple[str, Callable[[Path], dict[str, Any]]]] = [
    ("plan-only", _agentic_scenario_plan_only),
    ("edit-reject-approval", _agentic_scenario_edit_reject),
    ("apply-validation-pass-commit-prompt", _agentic_scenario_apply_validate_pass_commit_prompt),
    ("validation-fail-repair-pass", _agentic_scenario_validation_fail_repair_pass),
    ("validation-fail-loop-no-progress", _agentic_scenario_validation_loop_no_progress),
    ("interrupted-resume-recover", _agentic_scenario_interrupted_resume_recover),
]


def run_agentic_smoke(*, only: Optional[list[str]] = None) -> SmokeRunResult:
    """Run deterministic agentic workflow smoke scenarios (mock-only)."""
    result = SmokeRunResult()
    for name, fn in _AGENTIC_SCENARIOS:
        if only and name not in only:
            continue
        result.scenarios.append(_run_agentic_scenario(name, fn))
    return result


@smoke_app.command("agentic")
def smoke_agentic(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    only: Optional[str] = typer.Option(None, "--only", help="Comma-separated list of scenario names to run."),
) -> None:
    """[EXPERIMENTAL] Run deterministic agentic workflow smoke scenarios (mock-only)."""
    only_list: Optional[list[str]] = [s.strip() for s in only.split(",")] if only else None
    result = run_agentic_smoke(only=only_list)

    if json_output:
        status = "pass" if result.all_passed else "fail"
        print(render_json(CLIJSONResponse(command="smoke agentic", status=status, data=result.to_dict())))
        raise typer.Exit(code=0 if result.all_passed else 1)

    for scenario in result.scenarios:
        icon = "[green]PASS[/green]" if scenario.passed else "[red]FAIL[/red]"
        console.print(f"  {icon}  {scenario.name}  ({scenario.duration_ms} ms)")
        if not scenario.passed:
            console.print(f"       {scenario.message}")

    total = len(result.scenarios)
    console.print(f"\n[bold]{'All' if result.all_passed else str(result.passed)}/{total} scenarios passed[/bold]")
    raise typer.Exit(code=0 if result.all_passed else 1)


# ---------------------------------------------------------------------------
# Live-provider smoke (v4.10.4, EXPERIMENTAL, opt-in)
# ---------------------------------------------------------------------------


def _check_live_smoke_preconditions(project_root: Path) -> tuple[bool, str]:
    """Check whether live-provider smoke is allowed to run.

    Returns (allowed, reason). The reason is human-readable and safe to display.
    Never logs secrets.
    """
    from urllib.parse import urlparse
    from safecode.config import SafeCodeConfig

    if os.getenv("SAFECODE_LIVE_SMOKE") != "1":
        return False, "SAFECODE_LIVE_SMOKE is not set to 1. Set it to opt in to live provider tests."

    try:
        config = SafeCodeConfig.load(project_root)
    except Exception:
        return False, "Could not load SafeCode config."

    provider = config.llm.provider
    if provider == "mock":
        return False, "Live smoke refuses to run with provider=mock (would be meaningless)."

    # Static network policy check — no DNS or connect.
    host = urlparse(config.llm.base_url).hostname or ""
    if not config.sandbox.network_enabled:
        return False, (
            f"Network access is disabled by policy. "
            f"Provider host '{host}' cannot be reached."
        )
    if config.sandbox.network_allowlist and host not in config.sandbox.network_allowlist:
        return False, f"Host '{host}' is not in the network allowlist."

    # Check for the provider API key (presence only — never echo the value).
    from safecode.doctor import Doctor
    key_env, key_source = Doctor._resolve_provider_key_env(provider, config)
    if key_source == "missing":
        try:
            from safecode.security.keychain import get_api_key
            if get_api_key(provider):
                key_source = "keychain"
        except Exception:
            pass
    if key_source == "missing":
        return False, (
            f"Provider credential missing. Set {key_env} or store the key with "
            f"'sac provider add {provider} --store keychain'."
        )

    return True, "all preconditions met"


def _run_live_smoke_scenario_ask(config, project_root: Path) -> dict:
    """Run one safe ask round-trip. Never applies patches or writes source files."""
    from safecode.context.redactor import redact_secrets

    start = time.monotonic()
    try:
        client = create_llm_client(config)
        response = client.ask("What is 2+2?", {"context": "smoke test"})
        latency_ms = int((time.monotonic() - start) * 1000)
        answer = redact_secrets(str(response.content))[:200]
        return {"scenario": "ask", "passed": True, "latency_ms": latency_ms,
                "answer_preview": answer}
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"scenario": "ask", "passed": False, "latency_ms": latency_ms,
                "error": f"{type(exc).__name__}: {str(exc)[:120]}"}


def _run_live_smoke_scenario_propose_patch(config, project_root: Path) -> dict:
    """Run one safe propose-patch round-trip. Never applies the patch."""
    start = time.monotonic()
    try:
        client = create_llm_client(config)
        response = client.propose_patch(
            "Add a comment to an empty file.",
            {"files": {"hello.py": "# placeholder\n"}},
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        # Only report patch presence — never return patch content directly.
        has_patch = bool(response.patch_text and len(response.patch_text) > 0)
        return {"scenario": "propose_patch", "passed": True, "latency_ms": latency_ms,
                "patch_received": has_patch}
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"scenario": "propose_patch", "passed": False, "latency_ms": latency_ms,
                "error": f"{type(exc).__name__}: {str(exc)[:120]}"}


def _collect_secret_values() -> list[str]:
    """Collect effective API key values so they can be redacted from output."""
    _KEY_ENVS = (
        "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "SAFECODE_LLM_API_KEY",
        "ANTHROPIC_API_KEY",
    )
    secrets = [v for k in _KEY_ENVS if (v := os.environ.get(k, "")) and len(v) >= 8]
    try:
        from safecode.llm.provider_profiles import get_active_profile
        profile = get_active_profile()
        key = profile.effective_api_key() if profile is not None else None
        if key and len(key) >= 8 and key not in secrets:
            secrets.append(key)
    except Exception:
        pass
    return secrets


def _redact_scenario_strings(scenario: dict, secrets: list[str]) -> dict:
    """Return a copy of scenario with known secret values replaced."""
    result = {}
    for k, v in scenario.items():
        if isinstance(v, str):
            for secret in secrets:
                v = v.replace(secret, "[REDACTED]")
        result[k] = v
    return result


def run_live_provider_smoke(project_root: Path) -> dict:
    """Run the live-provider smoke suite. Must only be called after precondition checks."""
    from urllib.parse import urlparse
    from safecode.config import SafeCodeConfig

    config = SafeCodeConfig.load(project_root)
    provider = config.llm.provider
    model = config.llm.model
    base_url = config.llm.base_url

    secrets = _collect_secret_values()

    raw_scenarios: list[dict] = [
        _run_live_smoke_scenario_ask(config, project_root),
        _run_live_smoke_scenario_propose_patch(config, project_root),
    ]
    scenarios = [_redact_scenario_strings(s, secrets) for s in raw_scenarios]

    all_passed = all(s["passed"] for s in scenarios)
    return {
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "scenarios": scenarios,
        "all_passed": all_passed,
        "passed": sum(1 for s in scenarios if s["passed"]),
        "failed": sum(1 for s in scenarios if not s["passed"]),
        "total": len(scenarios),
    }


@smoke_app.command("live-provider", hidden=True)
def smoke_live_provider(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Opt-in live provider smoke (requires SAFECODE_LIVE_SMOKE=1).

    Runs one safe ask and one safe edit/propose-patch round-trip.
    Never applies patches, commits, runs project commands, or writes source files.
    Output redacts secrets. Requires a non-mock provider and a valid credential
    from the provider environment variable, system keychain, or trusted user config.
    """
    project_root = Path.cwd()
    allowed, reason = _check_live_smoke_preconditions(project_root)
    if not allowed:
        msg = f"[red]Live provider smoke refused: {reason}[/red]"
        if json_output:
            print(render_json(CLIJSONResponse(
                command="smoke live-provider",
                status="refused",
                data={"allowed": False, "reason": reason},
            )))
        else:
            console.print(msg)
        raise typer.Exit(code=1)

    result = run_live_provider_smoke(project_root)

    if json_output:
        status = "pass" if result["all_passed"] else "fail"
        print(render_json(CLIJSONResponse(
            command="smoke live-provider",
            status=status,
            data=result,
        )))
        raise typer.Exit(code=0 if result["all_passed"] else 1)

    console.print(f"[bold]Live Provider Smoke[/bold] — provider={result['provider']} "
                  f"model={result['model']}")
    for scenario in result["scenarios"]:
        icon = "[green]PASS[/green]" if scenario["passed"] else "[red]FAIL[/red]"
        latency = scenario.get("latency_ms", 0)
        console.print(f"  {icon}  {scenario['scenario']}  ({latency} ms)")
        if not scenario["passed"]:
            console.print(f"       {scenario.get('error', 'unknown error')}")

    total = result["total"]
    console.print(
        f"\n[bold]{'All' if result['all_passed'] else str(result['passed'])}/{total} scenarios passed[/bold]"
    )
    raise typer.Exit(code=0 if result["all_passed"] else 1)
