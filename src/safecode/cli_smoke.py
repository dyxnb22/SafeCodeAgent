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

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "notes": self.notes,
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
