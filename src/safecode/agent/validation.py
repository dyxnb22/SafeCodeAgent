"""EXPERIMENTAL validation loop for agentic apply steps (v4.11.3+)."""

from __future__ import annotations

import hashlib
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from safecode.agent.orchestrator import AgentOrchestrator
from safecode.agent.step_model import TypedAgentStep, TypedAgentStepResult
from safecode.config import SafeCodeConfig
from safecode.context.redactor import redact_secrets
from safecode.project.profile import ProfileCommand, ProjectProfile, load_profile
from safecode.shell.runner import ShellRunResult, ShellRunner
from safecode.state.journal import AgentJournalStore
from safecode.task.state import TaskIteration
from safecode.task.store import TaskStore


VALIDATION_ORDER: tuple[str, ...] = ("test", "lint", "typecheck", "build")
MAX_FAILURE_TAIL_CHARS = 4000


@dataclass(frozen=True)
class ValidationSuiteResult:
    """One suite command result from the validation loop."""

    suite: str
    command: tuple[str, ...]
    exit_code: int
    executed: bool
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ValidationLoopResult:
    """Summary returned by ``ValidationLoop.run_after_apply``."""

    status: str
    suite_results: tuple[ValidationSuiteResult, ...] = ()
    repair_iterations: int = 0
    failure_tail: str | None = None
    failure_tail_hash: str | None = None
    synthetic_fix_step: TypedAgentStep | None = None
    repair_proposed: bool = False
    stop_reason: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


class ValidationLoop:
    """Thin controller over project profiles, ShellRunner, journal, and edit().

    The loop intentionally does not parse a command string into a shell. Profile
    commands are stored as argv tuples; this controller converts them with
    ``shlex.join`` only because the existing ShellRunner/sac-run boundary accepts
    the command string and executes its classified token vector without
    ``shell=True``.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        shell_runner: ShellRunner | None = None,
        orchestrator: AgentOrchestrator | None = None,
        journal: AgentJournalStore | None = None,
        max_repair_iterations: int = 2,
    ) -> None:
        if max_repair_iterations < 0:
            raise ValueError("max_repair_iterations must be >= 0")
        self.project_root = project_root
        self.config = SafeCodeConfig.load(project_root)
        self.shell_runner = shell_runner or ShellRunner(project_root, self.config)
        self.orchestrator = orchestrator or AgentOrchestrator(project_root)
        self.journal = journal or AgentJournalStore(project_root)
        self.max_repair_iterations = max_repair_iterations

    def run_after_apply(
        self,
        *,
        session_id: str,
        step_index: int,
        goal: str,
        previous_failure_tail_hash: str | None = None,
        repair_iterations: int = 0,
    ) -> ValidationLoopResult:
        """Run configured validation after a successful apply-kind step."""
        profile = load_profile(self.project_root)
        if profile is None:
            note = "Validation skipped: no project profile found. Run 'sac profile detect' first."
            self._record_validation_result(session_id, step_index, "failed", note, "validation_skipped")
            return ValidationLoopResult(status="skipped", stop_reason="missing_profile", notes=(note,))

        commands = self._ordered_commands(profile)
        if not commands or commands[0][0] != "test":
            note = "Validation skipped: no test suite configured in project profile."
            self._record_validation_result(session_id, step_index, "failed", note, "validation_skipped")
            return ValidationLoopResult(status="skipped", stop_reason="missing_test_suite", notes=(note,))

        formatter_notes = self._run_optional_formatters(session_id)
        suite_results: list[ValidationSuiteResult] = []
        for suite, command in commands:
            result = self._run_suite(command)
            suite_result = ValidationSuiteResult(
                suite=suite,
                command=tuple(command.command),
                exit_code=result.exit_code,
                executed=result.executed,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
            suite_results.append(suite_result)
            self._record_suite_iteration(suite_result)
            self.journal.record_command(
                session_id,
                f"validation suite {suite} exited {result.exit_code}",
                {
                    "suite": suite,
                    "command": list(command.command),
                    "exit_code": result.exit_code,
                    "executed": result.executed,
                },
            )
            if result.exit_code != 0:
                return self._handle_failure(
                    session_id=session_id,
                    step_index=step_index,
                    goal=goal,
                    suite_results=tuple(suite_results),
                    failed_suite=suite,
                    shell_result=result,
                    previous_failure_tail_hash=previous_failure_tail_hash,
                    repair_iterations=repair_iterations,
                )

        summary = "Validation passed: " + ", ".join(result.suite for result in suite_results)
        self._record_validation_result(session_id, step_index, "success", summary, None)
        return ValidationLoopResult(
            status="success",
            suite_results=tuple(suite_results),
            stop_reason="validation_success",
            notes=tuple(formatter_notes),
        )

    def _ordered_commands(self, profile: ProjectProfile) -> list[tuple[str, ProfileCommand]]:
        commands: list[tuple[str, ProfileCommand]] = []
        for suite in VALIDATION_ORDER:
            command = getattr(profile, suite)
            if command is not None:
                commands.append((suite, command))
        return commands

    def _run_suite(self, command: ProfileCommand) -> ShellRunResult:
        return self.shell_runner.run(shlex.join(command.command), approved=True)

    def _run_optional_formatters(self, session_id: str) -> list[str]:
        if not self.config.formatter.enabled:
            return []
        try:
            from safecode.project.formatter import run_formatters

            results = run_formatters(
                self.project_root,
                approved=True,
                config=self.config,
                shell_runner=self.shell_runner,
            )
        except Exception as exc:
            return [f"Formatter skipped: {type(exc).__name__}"]
        notes: list[str] = []
        for result in results:
            note = f"Formatter {result.formatter} exited {result.exit_code}"
            notes.append(note)
            self.journal.record_command(
                session_id,
                note,
                {
                    "suite": "format",
                    "command": list(result.command),
                    "exit_code": result.exit_code,
                    "executed": result.executed,
                },
            )
        return notes

    def _handle_failure(
        self,
        *,
        session_id: str,
        step_index: int,
        goal: str,
        suite_results: tuple[ValidationSuiteResult, ...],
        failed_suite: str,
        shell_result: ShellRunResult,
        previous_failure_tail_hash: str | None,
        repair_iterations: int,
    ) -> ValidationLoopResult:
        failure_tail = _failure_tail(shell_result.stdout or "", shell_result.stderr or "")
        tail_hash = _tail_hash(failure_tail)
        summary = f"Validation failed in {failed_suite}; tail_hash={tail_hash}"
        self._record_validation_result(session_id, step_index, "failed", summary, "validation_failed")
        self.journal.record_failure(
            session_id,
            summary,
            {
                "failure_category": "validation_failed",
                "suite": failed_suite,
                "tail_hash": tail_hash,
                "failure_tail": failure_tail,
            },
        )

        if previous_failure_tail_hash and previous_failure_tail_hash == tail_hash:
            self._record_repair_iteration("loop_no_progress", tail_hash, None)
            return ValidationLoopResult(
                status="loop_no_progress",
                suite_results=suite_results,
                repair_iterations=repair_iterations,
                failure_tail=failure_tail,
                failure_tail_hash=tail_hash,
                stop_reason="loop_no_progress",
            )

        if repair_iterations >= self.max_repair_iterations:
            self._record_repair_iteration("max_repair_iterations", tail_hash, None)
            return ValidationLoopResult(
                status="max_repair_iterations",
                suite_results=suite_results,
                repair_iterations=repair_iterations,
                failure_tail=failure_tail,
                failure_tail_hash=tail_hash,
                stop_reason="max_repair_iterations",
            )

        fix_step = TypedAgentStep.from_route(
            index=step_index + 1,
            kind="fix",
            description=f"Propose repair for failed {failed_suite} validation.",
        )
        self.journal.record_typed_step(session_id, fix_step)
        from safecode.agent.repair import classify_failure, build_repair_prompt
        strategy = classify_failure(failure_tail, suite_name=failed_suite)
        repair_goal = build_repair_prompt(
            strategy,
            goal,
            failure_tail,
            failed_suite,
            diagnostics=self._type_diagnostics_block(),
        )
        pending_patch_id: str | None = None
        try:
            edit_result = self.orchestrator.edit(repair_goal)
            pending_patch_id = edit_result.proposal.id
            repair_summary = (
                f"Repair patch proposed for failed {failed_suite} validation; "
                "review/apply remains approval-gated."
            )
            repair_status = "waiting_for_user"
            repair_proposed = True
        except Exception as exc:
            repair_summary = f"Repair proposal failed: {type(exc).__name__}: {exc}"
            repair_status = "failed"
            repair_proposed = False

        self.journal.record_typed_result(
            session_id,
            TypedAgentStepResult(
                step_index=fix_step.index,
                kind="fix",
                status=repair_status,  # type: ignore[arg-type]
                summary=repair_summary,
                pending_patch_id=pending_patch_id,
                failure_category=None if repair_proposed else "repair_proposal_failed",
            ),
        )
        self._record_repair_iteration("repair_proposed" if repair_proposed else "failed", tail_hash, pending_patch_id)
        return ValidationLoopResult(
            status="repair_proposed" if repair_proposed else "repair_failed",
            suite_results=suite_results,
            repair_iterations=repair_iterations + 1,
            failure_tail=failure_tail,
            failure_tail_hash=tail_hash,
            synthetic_fix_step=fix_step,
            repair_proposed=repair_proposed,
            stop_reason="repair_proposed" if repair_proposed else "repair_failed",
        )

    def _record_validation_result(
        self,
        session_id: str,
        step_index: int,
        status: str,
        summary: str,
        failure_category: str | None,
    ) -> None:
        self.journal.record_typed_step(
            session_id,
            TypedAgentStep.from_route(index=step_index, kind="run", description="Run project validation suite."),
        )
        self.journal.record_typed_result(
            session_id,
            TypedAgentStepResult(
                step_index=step_index,
                kind="run",
                status="success" if status == "success" else "failed",
                summary=summary,
                failure_category=failure_category,
            ),
        )

    def _record_suite_iteration(self, result: ValidationSuiteResult) -> None:
        status = "passed" if result.exit_code == 0 else "failed"
        self._append_task_iteration(
            TaskIteration(
                iteration_index=0,
                event="validation",
                mode="agent",
                suite=result.suite,
                exit_code=result.exit_code,
                status=status,
            )
        )

    def _record_repair_iteration(
        self,
        status: str,
        tail_hash: str | None,
        pending_patch_id: str | None,
    ) -> None:
        self._append_task_iteration(
            TaskIteration(
                iteration_index=0,
                event="fix",
                mode="agent_validation",
                tail_hash=tail_hash,
                failure_tail_sha256=tail_hash,
                pending_patch_id=pending_patch_id,
                status=status,
                failure_category="loop_no_progress" if status == "loop_no_progress" else None,
            )
        )

    def _append_task_iteration(self, iteration: TaskIteration) -> None:
        store = TaskStore(self.project_root)
        task_id = store.current_id()
        if not task_id:
            return
        state = store.load(task_id)
        if state is None:
            return
        next_iteration = iteration.model_copy(update={"iteration_index": state.next_iteration_index()})
        store.save(state.model_copy(update={"iterations": list(state.iterations) + [next_iteration]}))

    def _type_diagnostics_block(self) -> str:
        """Return bounded Pyright diagnostics for repair prompts when available."""
        try:
            from safecode.index.lsp_bridge import PyrightBridge

            diagnostics = PyrightBridge.get_diagnostics(self.project_root)
        except Exception:
            return ""
        if not diagnostics:
            return ""
        lines: list[str] = []
        for diag in diagnostics[:10]:
            location = f"{diag.get('file', '')}:{diag.get('line', '')}:{diag.get('column', '')}"
            severity = diag.get("severity", "error")
            rule = diag.get("rule", "")
            message = str(diag.get("message", ""))[:240]
            rule_part = f" [{rule}]" if rule else ""
            lines.append(f"- {location} {severity}{rule_part}: {message}")
        return "\n".join(lines)[:2000]


def _failure_tail(stdout: str, stderr: str) -> str:
    combined = "\n".join(part for part in (stdout, stderr) if part)
    redacted = redact_secrets(combined)
    if len(redacted) <= MAX_FAILURE_TAIL_CHARS:
        return redacted
    return redacted[-MAX_FAILURE_TAIL_CHARS:]


def _tail_hash(tail: str) -> str:
    return hashlib.sha256(tail.encode("utf-8")).hexdigest()
