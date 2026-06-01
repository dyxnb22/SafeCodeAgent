"""Run local evaluation commands and task eval fixture replay.

Two independent layers live here:

1. ``EvalRunner`` / ``EvalCase`` — the original lightweight command runner
   (v2.4.x baseline). Preserved unchanged.

2. ``TaskReplayRunner`` / ``ReplayResult`` — deterministic replay runner for
   ``TaskEvalFixture`` (v2.5.1). No real LLM is invoked; ``setup_commands``
   simulate agent actions and ``validation_commands`` verify the resulting
   workspace state.
"""

from __future__ import annotations

import difflib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from safecode.eval.cases import EvalCase
from safecode.eval.failures import ClassifiedFailure, classify_replay_result
from safecode.eval.fixtures import TaskEvalFixture
from safecode.shell.runner import ShellRunner


# ── Legacy EvalRunner (preserved) ────────────────────────────────────────


@dataclass(frozen=True)
class EvalResult:
    """Evaluation result."""

    name: str
    passed: bool
    output: str


class EvalRunner:
    """Run deterministic local eval cases."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def run(self, cases: list[EvalCase]) -> list[EvalResult]:
        """Run eval cases."""
        shell = ShellRunner(self.project_root)
        results: list[EvalResult] = []
        for case in cases:
            result = shell.run(case.command, approved=True)
            output = result.stdout + result.stderr
            results.append(EvalResult(case.name, case.expected_text in output, output))
        return results


# ── Replay result models ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationCommandResult:
    """Result of one validation command run inside the replay workspace."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    passed: bool
    failure_reason: str | None = None


@dataclass
class ReplayResult:
    """Full result of a TaskEvalFixture replay.

    ``passed`` is ``True`` only when every specified constraint was met and no
    safety violation was detected.  ``failure_reasons`` enumerates every
    individual violation so callers can report precisely what went wrong.

    ``audit_events_status`` is ``"pending_no_session_replay_source"`` when the
    fixture lists ``safety.expect_audit_events`` but no live session is
    available to verify them — reported clearly rather than silently ignored.
    """

    fixture_name: str
    passed: bool
    failure_reasons: list[str]
    validation_details: list[ValidationCommandResult]
    observed_changed_files: list[str]
    workspace_diff: str
    network_intent: str  # "allowed" or "denied"
    forbidden_commands_violated: list[str]
    forbidden_file_writes_violated: list[str]
    audit_events_status: str
    workspace_path: str | None = None
    error: str | None = None
    classified_failures: list[ClassifiedFailure] = field(default_factory=list)


# ── TaskReplayRunner ──────────────────────────────────────────────────────


class WorkspaceError(RuntimeError):
    """Raised when workspace materialisation or setup fails."""


class TaskReplayRunner:
    """Deterministic replay runner for ``TaskEvalFixture``.

    Execution flow
    --------------
    1. Materialise a temporary workspace from ``fixture.repo``
       (inline: write files; local: ``shutil.copytree``).
    2. Snapshot the initial file state (before any commands).
    3. Run ``fixture.repo.setup_commands`` inside the workspace —
       these simulate what the agent applied.
    4. Snapshot the final file state; compute changed-file list and unified diff.
    5. Run ``fixture.validation_commands`` and collect output.
    6. Evaluate all specified constraints and safety checks.
    7. Return a ``ReplayResult``.

    No real LLM is involved. Real agent/LLM replay hooks can be injected in a
    future layer by subclassing or wrapping this runner.
    """

    _MAX_COMMAND_TIMEOUT = 60

    def run(self, fixture: TaskEvalFixture) -> ReplayResult:
        """Execute a fixture replay and return a ``ReplayResult``."""
        tmpdir: tempfile.TemporaryDirectory | None = None
        workspace: Path | None = None
        try:
            workspace, tmpdir = self._materialize_workspace(fixture)
        except WorkspaceError as exc:
            return self._error_result(fixture, str(exc))

        try:
            return self._run_in_workspace(fixture, workspace)
        finally:
            if tmpdir is not None:
                try:
                    tmpdir.cleanup()
                except OSError:
                    pass

    # ── internal ──────────────────────────────────────────────────────────

    def _materialize_workspace(
        self, fixture: TaskEvalFixture
    ) -> tuple[Path, tempfile.TemporaryDirectory]:
        tmpdir: tempfile.TemporaryDirectory = tempfile.TemporaryDirectory()
        workspace = Path(tmpdir.name)
        try:
            if fixture.repo.kind == "inline":
                for rel_path, content in fixture.repo.files.items():
                    target = workspace / rel_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")
            else:  # local
                src = Path(fixture.repo.path)  # type: ignore[arg-type]
                if not src.exists():
                    raise WorkspaceError(f"Local repo path does not exist: {src}")
                if not src.is_dir():
                    raise WorkspaceError(f"Local repo path is not a directory: {src}")
                shutil.copytree(src, workspace, dirs_exist_ok=True)
        except WorkspaceError:
            tmpdir.cleanup()
            raise
        except Exception as exc:
            tmpdir.cleanup()
            raise WorkspaceError(f"Workspace materialisation failed: {exc}") from exc
        return workspace, tmpdir

    def _run_in_workspace(self, fixture: TaskEvalFixture, workspace: Path) -> ReplayResult:
        failure_reasons: list[str] = []

        # Step 1: snapshot before agent simulation
        before = self._snapshot_files(workspace)

        # Step 2: run setup_commands (simulated agent actions)
        setup_error = self._run_setup_commands(fixture, workspace)
        if setup_error:
            failure_reasons.append(setup_error)

        # Step 3: snapshot after agent simulation; compute diff
        after = self._snapshot_files(workspace)
        observed_changed_files, workspace_diff = self._compute_diff(before, after)

        # Step 4: run validation commands
        cmd_timeout = min(fixture.timeout_seconds, self._MAX_COMMAND_TIMEOUT)
        validation_details: list[ValidationCommandResult] = []
        all_output = ""
        last_exit_code: int | None = None

        for cmd in fixture.validation_commands:
            detail = self._run_validation_command(cmd, workspace, cmd_timeout)
            validation_details.append(detail)
            all_output += detail.stdout + detail.stderr
            last_exit_code = detail.exit_code

        # Step 5: evaluate constraints

        # 5a. Validation command exit codes (default: all must exit 0)
        if fixture.expected.expected_exit_code is not None:
            # Only check the last command against the specified code
            if last_exit_code is not None and last_exit_code != fixture.expected.expected_exit_code:
                failure_reasons.append(
                    f"Expected last validation command exit code "
                    f"{fixture.expected.expected_exit_code}, got {last_exit_code}."
                )
        else:
            # All validation commands must exit 0
            for detail in validation_details:
                if not detail.passed and detail.failure_reason:
                    failure_reasons.append(detail.failure_reason)

        # 5b. expected_output_contains
        for needle in fixture.expected.expected_output_contains:
            if needle not in all_output:
                failure_reasons.append(
                    f"Expected output to contain {needle!r} but it was not found."
                )

        # 5c. expected_diff_contains
        for needle in fixture.expected.expected_diff_contains:
            if needle not in workspace_diff:
                failure_reasons.append(
                    f"Expected workspace diff to contain {needle!r} but it was not found."
                )

        # 5d. expected.expected_files_changed
        for path in fixture.expected.expected_files_changed:
            if path not in observed_changed_files:
                failure_reasons.append(
                    f"Expected file {path!r} to be changed but it was not."
                )

        # 5e. fixture-level expected_changed_files
        for path in fixture.expected_changed_files:
            if path not in observed_changed_files:
                failure_reasons.append(
                    f"Expected changed file {path!r} (expected_changed_files) was not changed."
                )

        # 5f. fixture-level forbidden_changed_files
        for path in fixture.forbidden_changed_files:
            if path in observed_changed_files:
                failure_reasons.append(
                    f"Forbidden file {path!r} was changed (forbidden_changed_files)."
                )

        # Step 6: safety checks

        # 6a. forbidden_file_writes from safety: check against observed changed files
        forbidden_writes_violated: list[str] = []
        for pattern in fixture.safety.forbidden_file_writes:
            for obs in observed_changed_files:
                if obs == pattern or obs.endswith("/" + pattern) or obs == pattern.lstrip("/"):
                    forbidden_writes_violated.append(pattern)
                    failure_reasons.append(
                        f"Safety violation: forbidden file write {pattern!r} was detected."
                    )
                    break

        # 6b. forbidden_commands from safety: check against run commands
        # In this layer we can only compare against validation_commands we ran.
        forbidden_cmds_violated: list[str] = []
        run_cmds = [d.command for d in validation_details]
        for pattern in fixture.safety.forbidden_commands:
            for cmd in run_cmds:
                if pattern in cmd:
                    forbidden_cmds_violated.append(pattern)
                    failure_reasons.append(
                        f"Safety violation: forbidden command pattern {pattern!r} "
                        "observed in validation commands."
                    )
                    break

        # 6c. Audit events: no live session available — report clearly, fail closed
        audit_events_status: str
        if fixture.safety.expect_audit_events:
            audit_events_status = "pending_no_session_replay_source"
        else:
            audit_events_status = "ok"

        # 6d. Network intent (informational; enforcement is future work)
        network_intent = "allowed" if fixture.safety.allow_network else "denied"

        result = ReplayResult(
            fixture_name=fixture.name,
            passed=len(failure_reasons) == 0,
            failure_reasons=failure_reasons,
            validation_details=validation_details,
            observed_changed_files=observed_changed_files,
            workspace_diff=workspace_diff,
            network_intent=network_intent,
            forbidden_commands_violated=forbidden_cmds_violated,
            forbidden_file_writes_violated=forbidden_writes_violated,
            audit_events_status=audit_events_status,
            workspace_path=str(workspace),
            error=None,
        )
        result.classified_failures = classify_replay_result(result)
        return result

    def _run_setup_commands(self, fixture: TaskEvalFixture, workspace: Path) -> str | None:
        """Run repo setup_commands; return an error string on first failure."""
        cmd_timeout = min(fixture.timeout_seconds, self._MAX_COMMAND_TIMEOUT)
        for cmd in fixture.repo.setup_commands:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=workspace,
                    shell=True,
                    text=True,
                    capture_output=True,
                    timeout=cmd_timeout,
                )
                if result.returncode != 0:
                    return (
                        f"Setup command failed (exit {result.returncode}): {cmd!r} — "
                        f"{result.stderr.strip()}"
                    )
            except subprocess.TimeoutExpired:
                return f"Setup command timed out after {cmd_timeout}s: {cmd!r}"
        return None

    def _run_validation_command(
        self, command: str, workspace: Path, timeout_seconds: int
    ) -> ValidationCommandResult:
        try:
            result = subprocess.run(
                command,
                cwd=workspace,
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
            passed = result.returncode == 0
            return ValidationCommandResult(
                command=command,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                passed=passed,
                failure_reason=(
                    f"Validation command exited with code {result.returncode}: {command!r}"
                    if not passed
                    else None
                ),
            )
        except subprocess.TimeoutExpired:
            return ValidationCommandResult(
                command=command,
                exit_code=124,
                stdout="",
                stderr="",
                passed=False,
                failure_reason=f"Validation command timed out after {timeout_seconds}s: {command!r}",
            )

    def _snapshot_files(self, workspace: Path) -> dict[str, str]:
        """Return ``{relative_path: content}`` for all files in workspace."""
        snapshot: dict[str, str] = {}
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(workspace))
            try:
                snapshot[rel] = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                snapshot[rel] = "<unreadable>"
        return snapshot

    def _compute_diff(
        self, before: dict[str, str], after: dict[str, str]
    ) -> tuple[list[str], str]:
        """Return ``(changed_files, unified_diff_text)``."""
        all_paths = sorted(set(before) | set(after))
        changed: list[str] = []
        diff_parts: list[str] = []

        for path in all_paths:
            before_content = before.get(path, "")
            after_content = after.get(path, "")
            if before_content == after_content:
                continue
            changed.append(path)
            diff = list(
                difflib.unified_diff(
                    before_content.splitlines(keepends=True),
                    after_content.splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
            diff_parts.append("".join(diff))

        return changed, "\n".join(diff_parts)

    @staticmethod
    def _error_result(fixture: TaskEvalFixture, error: str) -> ReplayResult:
        result = ReplayResult(
            fixture_name=fixture.name,
            passed=False,
            failure_reasons=[error],
            validation_details=[],
            observed_changed_files=[],
            workspace_diff="",
            network_intent="allowed" if fixture.safety.allow_network else "denied",
            forbidden_commands_violated=[],
            forbidden_file_writes_violated=[],
            audit_events_status="pending_no_session_replay_source"
            if fixture.safety.expect_audit_events
            else "ok",
            workspace_path=None,
            error=error,
        )
        result.classified_failures = classify_replay_result(result)
        return result
