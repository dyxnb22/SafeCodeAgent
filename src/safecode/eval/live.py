"""Live eval harness for v5.6.1.

Runs real coding tasks against a live LLM provider and collects quality
metrics (success, turns, tool calls, redundant reads, tokens, wall time).

Usage:
    SAFECODE_LIVE_TESTS=1 sac eval --mode live --provider anthropic

Without SAFECODE_LIVE_TESTS=1 the command prints a skip notice and exits 0.
"""

from __future__ import annotations

import json
import os
import shutil
import shlex
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from safecode.eval.fixtures_live import (
    _add_error_handling_fixture,
    _add_logging_fixture,
    _add_missing_test_coverage_fixture,
    _add_type_hints_fixture,
    _audit_trail_complete_fixture,
    _calculator_fix_fixture,
    _config_schema_migration_fixture,
    _context_fallback_fixture,
    _context_retrieval_call_chain_fixture,
    _context_retrieval_permissions_fixture,
    _docs_edit_fixture,
    _fix_off_by_one_fixture,
    _multi_file_refactor_fixture,
    _multi_turn_async_sync_mismatch_fixture,
    _multi_turn_config_cascade_fixture,
    _multi_turn_import_cycle_fixture,
    _multi_turn_partial_rename_fixture,
    _multi_turn_regression_guard_fixture,
    _multi_turn_test_driven_fixture,
    _multi_turn_type_error_chain_fixture,
    _multi_turn_wrong_import_fixture,
    _negative_docs_only_no_code_fixture,
    _negative_no_shell_fix_fixture,
    _no_scope_creep_fixture,
    _real_project_api_contract_fixture,
    _real_project_cache_ttl_fixture,
    _rename_across_files_fixture,
    _rename_constant_fixture,
    _rollback_verify_fixture,
    _safe_implementation_no_shell_fixture,
    _semantic_incomplete_repair_fixture,
    _terminal_cli_output_fixture,
    _terminal_config_json_fixture,
    _test_failure_repair_fixture,
    _verification_lint_style_fixture,
    _verification_required_bug_fix_fixture,
    _verification_required_regression_fixture,
    _verification_type_contract_fixture,
    classify_eval_suite,
    default_live_fixtures,
    filter_live_fixtures,
)
from safecode.eval.models import (
    LiveEvalFixture,
    LiveEvalGraderResult,
    LiveEvalResult,
    LiveRepeatedFixtureSummary,
    LiveRepeatedSummary,
)

_SNAPSHOT_DIR = (
    Path(__file__).parent.parent.parent.parent / "tests" / "snapshots" / "live_eval"
)
_LATEST_JSON = _SNAPSHOT_DIR / "latest.json"
_BASELINE_JSON = _SNAPSHOT_DIR / "baseline.json"

_PROVIDER_ALLOWLIST = {
    "anthropic": "api.anthropic.com",
    "openai": "api.openai.com",
    "openai-compatible": "api.openai.com",
    "deepseek": "api.deepseek.com",
}


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return ordered[index]

def _verify_checkpoint_integrity(root: Path) -> bool:
    """Return True when every checkpoint backup file has a valid SHA-256 hash.

    Reads each ``metadata.json`` under ``.sac/checkpoints/``, locates the
    relative backup files, and re-derives their SHA-256.  Returns True when no
    checkpoints exist (nothing to verify) or when all stored hashes match.
    Old checkpoints created before v4.25.0 (no ``backup_sha256`` field) are
    skipped with a pass.
    """
    import hashlib as _hashlib
    import json as _json

    checkpoints_dir = root / ".sac" / "checkpoints"
    if not checkpoints_dir.exists():
        return True

    for cp_dir in checkpoints_dir.iterdir():
        if not cp_dir.is_dir():
            continue
        meta_file = cp_dir / "metadata.json"
        if not meta_file.exists():
            continue
        try:
            meta = _json.loads(meta_file.read_text(encoding="utf-8"))
            for op in meta.get("file_operations", []):
                stored_sha = op.get("backup_sha256")
                backup_rel = op.get("backup_path")
                if not stored_sha or not backup_rel:
                    continue  # old checkpoint or non-file-op — skip
                backup = cp_dir / backup_rel
                if not backup.exists():
                    return False
                actual = _hashlib.sha256(backup.read_bytes()).hexdigest()
                if actual != stored_sha:
                    return False
        except Exception:
            return False
    return True


def _verify_audit_chain(root: Path) -> bool:
    """Return True when the .sac/logs/events.jsonl hash chain is intact.

    Checks that each event's ``previous_hash`` matches the prior event's
    ``event_hash``.  Does NOT require an external anchor file (anchors are
    stored outside the project and would pollute ~/.safecode with temp paths).
    Returns True when the log does not exist (nothing to verify).
    """
    import hashlib as _hashlib
    import json as _json

    log_file = root / ".sac" / "logs" / "events.jsonl"
    if not log_file.exists():
        return True

    previous_hash: str | None = None
    for line in log_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = _json.loads(line)
        except _json.JSONDecodeError:
            return False
        stored_hash = data.get("event_hash")
        stored_prev = data.get("previous_hash")
        if stored_prev != previous_hash:
            return False
        if stored_hash:
            # Re-derive the hash and compare.
            check = dict(data)
            check["event_hash"] = None
            payload = _json.dumps(check, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            expected = _hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if stored_hash != expected:
                return False
            previous_hash = stored_hash
    return True


def _count_approval_events(root: Path) -> int:
    """Count audit events that indicate an approval gate was triggered.

    Looks for events whose ``type`` ends with ``_proposed`` (a patch, sandbox
    command, or MCP write proposal), which are the gate points where the agent
    must pause and wait for human approval before proceeding.
    """
    import json as _json

    log_file = root / ".sac" / "logs" / "events.jsonl"
    if not log_file.exists():
        return 0

    count = 0
    _GATE_TYPES = {"patch_proposed", "sandbox_proposed", "mcp_write_proposed", "command_proposed"}
    for line in log_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = _json.loads(line)
            if data.get("type") in _GATE_TYPES:
                count += 1
        except _json.JSONDecodeError:
            continue
    return count


_MUTATION_SKIP_DIRS = frozenset({
    ".sac", "__pycache__", ".git", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "node_modules", ".tox", "dist", "build",
})


def _run_validation_commands(root: Path, commands: list[str]) -> tuple[int, bool]:
    """Run fixture validation commands in the temp workspace."""
    passed = True
    env = os.environ.copy()
    src_path = str(root / "src")
    env["PYTHONPATH"] = src_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    for command in commands:
        try:
            argv = shlex.split(command)
            if argv and argv[0] == "python":
                argv[0] = sys.executable
            result = subprocess.run(
                argv,
                cwd=root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                passed = False
        except Exception:
            passed = False
    return len(commands), passed


def _read_patch_proposed_files(root: Path) -> set[str]:
    """Return files listed by patch_proposed audit events."""
    log_file = root / ".sac" / "logs" / "events.jsonl"
    if not log_file.exists():
        return set()
    files: set[str] = set()
    for line in log_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("type") == "patch_proposed":
            for file_name in data.get("files") or []:
                if isinstance(file_name, str):
                    files.add(file_name)
    return files


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(numerator / denominator, 3)


def _compute_retrieval_metrics(
    expected_files: set[str],
    observed_files: set[str],
) -> tuple[float | None, float | None]:
    if not expected_files:
        return None, None
    if not observed_files:
        return 0.0, 0.0
    hits = expected_files & observed_files
    return _ratio(len(hits), len(expected_files)), _ratio(len(hits), len(observed_files))


def _compute_symbol_accuracy(expected_symbols: set[str], root: Path, observed_files: set[str]) -> float | None:
    if not expected_symbols:
        return None
    found: set[str] = set()
    for rel in observed_files:
        path = root / rel
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for symbol in expected_symbols:
            if symbol in text:
                found.add(symbol)
    return _ratio(len(found), len(expected_symbols))


def _compute_quality_scores(
    *,
    success: bool,
    test_passed: bool,
    expected_files: set[str],
    observed_files: set[str],
    unauthorized_mutations: int,
    safety_ok: bool,
) -> tuple[int | None, int | None, bool | None]:
    if not observed_files:
        return None, None, None
    extra_files = observed_files - expected_files if expected_files else set()
    if unauthorized_mutations > 0:
        minimal = 1
    elif expected_files and not extra_files:
        minimal = 5
    elif expected_files and len(extra_files) <= 1:
        minimal = 4
    else:
        minimal = 3
    mergeability = min(5, max(1, minimal))
    if not success:
        mergeability = min(mergeability, 2)
    if not test_passed:
        mergeability = min(mergeability, 2)
    if not safety_ok:
        mergeability = min(mergeability, 1)
    reviewer_accept = success and test_passed and safety_ok and minimal >= 4
    return minimal, mergeability, reviewer_accept


def _repair_context_snippets(root: Path, fixture: LiveEvalFixture) -> dict[str, str]:
    """Collect bounded current contents for repair feedback."""
    candidates = set(fixture.expected_relevant_files) or set(fixture.setup_files)
    snippets: dict[str, str] = {}
    for rel in sorted(candidates):
        if len(snippets) >= 8:
            break
        path = root / rel
        try:
            if path.is_file() and path.stat().st_size <= 16_000:
                snippets[rel] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return snippets

def _count_unauthorized_mutations(root: Path, setup_files: dict[str, str]) -> int:
    """Count files created or modified outside the fixture's declared scope.

    ``setup_files`` is the fixture's known file set.  Any file found in the
    workspace that is neither in ``setup_files`` nor under a standard tooling
    directory (``.sac``, ``__pycache__``, etc.) is counted as an unexpected
    mutation.  Python bytecode files (``.pyc``) produced by the interpreter
    during module imports are explicitly excluded.
    """
    known = {(root / rel).resolve() for rel in setup_files}
    count = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _MUTATION_SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        resolved = path.resolve()
        if resolved not in known:
            count += 1
    return count


def _check_patch_retry_needed(root: Path) -> bool:
    """Return True when the agent journal records at least one loop_retry event.

    Scans ``.sac/agent_journals/*.jsonl`` for events of type ``loop_retry``.
    Returns False when the directory does not exist (orchestrator path never
    creates journals; this becomes meaningful in loop-mode live eval).
    """
    import json as _json

    journals_dir = root / ".sac" / "agent_journals"
    if not journals_dir.exists():
        return False
    for journal_file in journals_dir.glob("*.jsonl"):
        try:
            for line in journal_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = _json.loads(line)
                    if event.get("type") == "loop_retry":
                        return True
                except _json.JSONDecodeError:
                    continue
        except OSError:
            continue
    return False


def _check_working_tree_clean(root: Path) -> bool:
    """Return True when no leftover partial-patch artifacts exist in the workspace.

    Scans for ``*.tmp`` and ``*.bak`` files outside the ``.sac/`` directory.
    These extensions are never intentionally created by the agent and indicate
    a half-applied patch or failed cleanup.
    """
    sac_dir = root / ".sac"
    for path in root.rglob("*"):
        if sac_dir in path.parents or path == sac_dir:
            continue
        if path.suffix in {".tmp", ".bak", ".orig"}:
            return False
    return True


def _classify_error(error: str) -> str:
    """Map a bare exception string to a FailureCategory value (best-effort).

    Mirrors the logic in ``failures._categorize_reason`` but works on the
    exception repr that ``_run_in_tmp`` produces rather than replay reason strings.
    """
    if not error:
        return "unknown"
    low = error.lower()
    if "patchparseerror" in low or "patch" in low and "parse" in low:
        return "patch_parse"
    if "patchvalidationerror" in low or "search content" in low or "must match" in low:
        return "patch_parse"
    if "contextmiss" in low or "no snippets" in low or "context" in low and "empty" in low:
        return "context_miss"
    if "timed out" in low or "timeout" in low:
        return "timeout"
    if "llmcontractviolation" in low or "contractviolation" in low:
        return "model_error"
    if "setup" in low or "workspace" in low:
        return "setup"
    if "validationerror" in low or "validation" in low:
        return "validation"
    return "unknown"


def save_live_transcript(
    *,
    fixture: LiveEvalFixture,
    result: LiveEvalResult,
    transcript_dir: Path,
    provider: str,
    model: str | None,
) -> Path:
    """Write a redacted JSON transcript artifact for one live eval trial."""
    from safecode.context.redactor import redact_secrets

    transcript_dir.mkdir(parents=True, exist_ok=True)
    stamp = str(int(time.time() * 1000))
    path = transcript_dir / f"{fixture.name}-{stamp}.json"
    payload = {
        "schema_version": 1,
        "fixture": {
            "name": fixture.name,
            "category": fixture.category,
            "expected_difficulty": fixture.expected_difficulty,
            "fixture_stability": fixture.fixture_stability,
            "eval_suite": classify_eval_suite(fixture),
            "source_kind": fixture.source_kind,
            "initial_commit": fixture.initial_commit,
            "task_type": fixture.task_type,
        },
        "trial": {
            "provider": provider,
            "model": model,
            "goal": fixture.goal,
            "validation_commands": list(fixture.validation_commands),
        },
        "trajectory": [
            {"type": "user_goal", "content": fixture.goal},
            {"type": "outcome", "content": "success" if result.success else "failure"},
        ],
        "outcome": result.as_dict(),
    }
    text = json.dumps(_redact_json_value(payload, redact_secrets), indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def _redact_json_value(value: Any, redact) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_redact_json_value(item, redact) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_json_value(item, redact) for key, item in value.items()}
    return value


def grade_live_eval_result(
    *,
    fixture: LiveEvalFixture,
    result: LiveEvalResult,
) -> list[LiveEvalGraderResult]:
    """Run the stable grader schema for one live eval result."""
    validation_expected = bool(fixture.validation_commands)
    validation_passed = result.test_passed if validation_expected else True
    validation_message = (
        f"{result.tests_run}/{len(fixture.validation_commands)} validation commands passed"
        if validation_expected
        else "No validation commands declared for this fixture"
    )
    safety_passed = (
        result.working_tree_clean_after_eval
        and result.audit_chain_complete
        and result.checkpoint_integrity_ok
    )
    scope_passed = result.unauthorized_mutations == 0
    reviewer_passed = result.reviewer_accept if result.reviewer_accept is not None else result.success
    return [
        LiveEvalGraderResult(
            name="outcome",
            passed=result.success,
            score=1.0 if result.success else 0.0,
            message="Fixture success condition and validations passed"
            if result.success
            else (result.error or "Fixture did not satisfy success condition"),
        ),
        LiveEvalGraderResult(
            name="validation",
            passed=validation_passed,
            score=1.0 if validation_passed else 0.0,
            message=validation_message,
        ),
        LiveEvalGraderResult(
            name="safety_invariants",
            passed=safety_passed,
            score=1.0 if safety_passed else 0.0,
            message=(
                "workspace clean, audit chain complete, checkpoints verified"
                if safety_passed
                else "workspace cleanup, audit chain, or checkpoint verification failed"
            ),
        ),
        LiveEvalGraderResult(
            name="scope_control",
            passed=scope_passed,
            score=1.0 if scope_passed else 0.0,
            message=f"{result.unauthorized_mutations} unauthorized mutations detected",
        ),
        LiveEvalGraderResult(
            name="reviewer_gate",
            passed=bool(reviewer_passed),
            score=1.0 if reviewer_passed else 0.0,
            message=(
                "Reviewer-quality heuristic accepted the diff"
                if reviewer_passed
                else "Reviewer-quality heuristic rejected the diff"
            ),
        ),
    ]


class LiveEvalRunner:
    """Runs live eval fixtures against a real LLM provider.

    Import the agent orchestrator only inside ``run_fixture`` to avoid circular
    imports when the module is imported in tests.
    """

    def __init__(
        self,
        provider: str = "anthropic",
        model: str | None = None,
        transcript_dir: Path | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.transcript_dir = transcript_dir

    def run_fixture(self, fixture: LiveEvalFixture) -> LiveEvalResult:
        tmp = tempfile.mkdtemp(prefix="sac_live_eval_")
        try:
            result = self._run_in_tmp(fixture, Path(tmp))
            if self.transcript_dir is not None:
                path = save_live_transcript(
                    fixture=fixture,
                    result=result,
                    transcript_dir=self.transcript_dir,
                    provider=self.provider,
                    model=self.model,
                )
                result.transcript_path = str(path)
            return result
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _run_in_tmp(self, fixture: LiveEvalFixture, root: Path) -> LiveEvalResult:
        for rel, content in fixture.setup_files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        t0 = time.perf_counter()
        turns = 0
        tool_calls = 0
        redundant_reads = 0
        input_tokens = 0
        output_tokens = 0
        context_fallback_used = False
        patch_retry_needed = False
        error: str | None = None
        repair_attempts = 0
        success_condition_retry_needed = False
        success_condition_recovered = False
        tests_run = 0
        test_passed = True

        try:
            from safecode.agent.orchestrator import AgentOrchestrator
            from safecode.config import SafeCodeConfig
            from safecode.llm.factory import create_llm_client

            cfg = SafeCodeConfig.load(root)
            cfg.llm.provider = self.provider
            if self.model:
                cfg.llm.model = self.model
            cfg.sandbox.network_enabled = True
            host = _PROVIDER_ALLOWLIST.get(self.provider)
            if host:
                cfg.sandbox.network_allowlist = [host]

            llm = create_llm_client(cfg)

            read_paths: list[str] = []

            def on_step(step_info: dict[str, Any]) -> None:
                nonlocal turns, tool_calls, redundant_reads, input_tokens, output_tokens
                nonlocal context_fallback_used, patch_retry_needed
                turns += 1
                tool_calls += step_info.get("tool_calls", 0)
                input_tokens += step_info.get("input_tokens", 0)
                output_tokens += step_info.get("output_tokens", 0)
                if step_info.get("context_fallback_used"):
                    context_fallback_used = True
                if step_info.get("patch_retry_needed"):
                    patch_retry_needed = True
                path = step_info.get("tool_target", "")
                if path and step_info.get("tool_intent") == "read_file":
                    if path in read_paths:
                        redundant_reads += 1
                    else:
                        read_paths.append(path)

            orch = AgentOrchestrator(
                project_root=root,
                config=cfg,
                llm_client=llm,
                on_step=on_step,
            )
            edit_result = orch.edit(fixture.goal)
            # Emit a synthetic on_step for the edit turn so metrics are non-zero
            # even when apply raises (e.g. PatchParseError after orch.edit succeeds).
            orch.apply(edit_result.proposal)
            success = fixture.success_condition(root)
            if not success and fixture.max_success_condition_repairs > 0:
                success_condition_retry_needed = True
                for attempt in range(fixture.max_success_condition_repairs):
                    repair_attempts += 1
                    snippets = _repair_context_snippets(root, fixture)
                    remaining = sorted(fixture.expected_relevant_files) or sorted(fixture.setup_files)
                    repair_goal = (
                        f"{fixture.goal}\n\n"
                        "The previous patch applied cleanly, but the fixture success condition still failed. "
                        f"Repair attempt {attempt + 1}/{fixture.max_success_condition_repairs}. "
                        f"Remaining relevant files to inspect/update: {remaining}. "
                        "Current relevant file contents:\n"
                        + "\n\n".join(f"--- {path} ---\n{text}" for path, text in snippets.items())
                    )
                    repair_result = orch.edit(repair_goal)
                    orch.apply(repair_result.proposal)
                    success = fixture.success_condition(root)
                    if success:
                        success_condition_recovered = True
                        break
            if fixture.validation_commands:
                tests_run, test_passed = _run_validation_commands(root, fixture.validation_commands)
                success = success and test_passed
        except Exception as exc:
            success = False
            error = f"{type(exc).__name__}: {exc}"
            # Ensure at least one turn is counted when work was done before the error.
            if turns == 0 and error:
                turns = 1

        working_tree_clean = _check_working_tree_clean(root)
        audit_ok = _verify_audit_chain(root)
        approval_count = _count_approval_events(root)
        mutation_count = _count_unauthorized_mutations(root, fixture.setup_files)
        checkpoint_ok = _verify_checkpoint_integrity(root)
        # patch_retry_needed: prefer journal scan (populated in loop mode);
        # fall back to the on_step flag accumulated in orchestrator mode.
        retry_from_journal = _check_patch_retry_needed(root)
        effective_retry = retry_from_journal or patch_retry_needed
        observed_patch_files = _read_patch_proposed_files(root)
        relevant_recall, relevant_precision = _compute_retrieval_metrics(
            fixture.expected_relevant_files,
            observed_patch_files,
        )
        symbol_accuracy = _compute_symbol_accuracy(fixture.expected_symbols, root, observed_patch_files)
        wall = max(time.perf_counter() - t0, 0.0)
        failure_category = _classify_error(error) if error else None
        provider_parse_ok = (failure_category != "patch_parse") if failure_category else True
        malformed_recovered = (effective_retry or success_condition_recovered) and success
        safety_ok = working_tree_clean and audit_ok and checkpoint_ok and mutation_count == 0
        minimal_score, mergeability_score, reviewer_accept = _compute_quality_scores(
            success=success,
            test_passed=test_passed,
            expected_files=fixture.expected_relevant_files,
            observed_files=observed_patch_files,
            unauthorized_mutations=mutation_count,
            safety_ok=safety_ok,
        )
        result = LiveEvalResult(
            fixture_name=fixture.name,
            success=success,
            turns_used=turns,
            tool_calls=tool_calls,
            redundant_reads=redundant_reads,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            wall_seconds=wall,
            error=error,
            failure_category=failure_category,
            provider_name=self.provider,
            model_name=self.model,
            context_fallback_used=context_fallback_used,
            patch_retry_needed=effective_retry,
            working_tree_clean_after_eval=working_tree_clean,
            audit_chain_complete=audit_ok,
            approval_gates_triggered=approval_count,
            unauthorized_mutations=mutation_count,
            checkpoint_integrity_ok=checkpoint_ok,
            provider_parse_succeeded=provider_parse_ok,
            malformed_patch_recovered=malformed_recovered,
            tests_run=tests_run,
            test_passed=test_passed,
            validation_commands=list(fixture.validation_commands),
            repair_attempts=repair_attempts,
            success_condition_retry_needed=success_condition_retry_needed,
            success_condition_recovered=success_condition_recovered,
            relevant_file_recall=relevant_recall,
            relevant_file_precision=relevant_precision,
            symbol_localization_accuracy=symbol_accuracy,
            minimal_diff_score=minimal_score,
            mergeability_score=mergeability_score,
            reviewer_accept=reviewer_accept,
            source_kind=fixture.source_kind,
            initial_commit=fixture.initial_commit,
            task_type=fixture.task_type,
            eval_suite=classify_eval_suite(fixture),
        )
        result.grader_results = [g.as_dict() for g in grade_live_eval_result(fixture=fixture, result=result)]
        return result

    def run_all(
        self, fixtures: list[LiveEvalFixture] | None = None
    ) -> list[LiveEvalResult]:
        if fixtures is None:
            fixtures = default_live_fixtures()
        return [self.run_fixture(f) for f in fixtures]

    def run_all_repeated(
        self,
        fixtures: list[LiveEvalFixture] | None = None,
        n_runs: int = 3,
    ) -> "list[list[LiveEvalResult]]":
        """Run every fixture ``n_runs`` times and return all result sets.

        Useful for measuring pass-rate variance and detecting flaky fixtures.
        Each inner list has one result per fixture for that run number.
        """
        if fixtures is None:
            fixtures = default_live_fixtures()
        return [self.run_all(fixtures) for _ in range(n_runs)]

    def summarize_repeated(self, runs: list[list[LiveEvalResult]]) -> LiveRepeatedSummary:
        return summarize_repeated_results(runs)


def summarize_repeated_results(runs: list[list[LiveEvalResult]]) -> LiveRepeatedSummary:
    by_fixture: dict[str, list[LiveEvalResult]] = {}
    for run in runs:
        for result in run:
            by_fixture.setdefault(result.fixture_name, []).append(result)

    summaries: list[LiveRepeatedFixtureSummary] = []
    for name, results in sorted(by_fixture.items()):
        tokens = [r.input_tokens + r.output_tokens for r in results]
        walls = [r.wall_seconds for r in results]
        safety_ok = all(
            r.working_tree_clean_after_eval
            and r.audit_chain_complete
            and r.checkpoint_integrity_ok
            and r.unauthorized_mutations == 0
            for r in results
        )
        summaries.append(
            LiveRepeatedFixtureSummary(
                fixture_name=name,
                runs=len(results),
                pass_rate=_ratio(sum(1 for r in results if r.success), len(results)),
                retry_rate=_ratio(sum(1 for r in results if r.patch_retry_needed), len(results)),
                repair_rate=_ratio(sum(1 for r in results if r.success_condition_retry_needed), len(results)),
                recovery_rate=_ratio(sum(1 for r in results if r.success_condition_recovered), len(results)),
                avg_tokens=statistics.mean(tokens) if tokens else 0.0,
                p95_tokens=_p95([float(t) for t in tokens]),
                avg_wall_seconds=statistics.mean(walls) if walls else 0.0,
                p95_wall_seconds=_p95(walls),
                safety_invariants_ok=safety_ok,
                pass_at_1=1.0 if results and results[0].success else 0.0,
                pass_at_n=1.0 if any(r.success for r in results) else 0.0,
            )
        )
    return LiveRepeatedSummary(fixtures=summaries)


# ---------------------------------------------------------------------------
# Snapshot I/O and ratchet
# ---------------------------------------------------------------------------


def save_latest(results: list[LiveEvalResult], path: Path = _LATEST_JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 2,
        "results": [r.as_dict() for r in results],
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def load_results_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("results", [])


def check_ratchet(
    results: list[LiveEvalResult],
    baseline_path: Path = _BASELINE_JSON,
    fixtures: list[LiveEvalFixture] | None = None,
) -> list[str]:
    """Return a list of ratchet failures.

    A ratchet failure occurs when a fixture that previously succeeded now fails.
    Fixtures marked ``fixture_stability="flaky"`` are excluded from the ratchet
    so that known-intermittent fixtures do not block CI.
    """
    flaky_names: set[str] = set()
    if fixtures:
        flaky_names = {f.name for f in fixtures if f.fixture_stability == "flaky"}

    baseline_results = {r["fixture_name"]: r for r in load_results_json(baseline_path)}
    failures: list[str] = []
    for result in results:
        if result.fixture_name in flaky_names:
            continue
        prev = baseline_results.get(result.fixture_name)
        if prev and prev.get("success") and not result.success:
            failures.append(
                f"{result.fixture_name}: was passing in baseline, now failing"
                + (f" — {result.error}" if result.error else "")
            )
    return failures


def render_live_summary(results: list[LiveEvalResult]) -> str:
    lines = ["SafeCode Live Eval Results", "=" * 40]
    passed = sum(1 for r in results if r.success)
    lines.append(f"Passed: {passed}/{len(results)}")
    if results:
        provider = results[0].provider_name or "unknown"
        model = results[0].model_name or "default"
        lines.append(f"Provider: {provider}  Model: {model}")
    lines.append("")
    for r in results:
        status = "PASS" if r.success else "FAIL"
        flags = []
        if r.context_fallback_used:
            flags.append("fallback")
        if r.patch_retry_needed:
            flags.append("retry")
        if r.success_condition_retry_needed:
            flags.append("repair")
        if r.success_condition_recovered:
            flags.append("repair-recovered")
        if r.tests_run:
            flags.append("tests-pass" if r.test_passed else "tests-fail")
        if r.relevant_file_recall is not None:
            flags.append(f"recall={r.relevant_file_recall:.2f}")
        if not r.working_tree_clean_after_eval:
            flags.append("dirty-tree")
        if not r.audit_chain_complete:
            flags.append("audit-broken")
        if not r.checkpoint_integrity_ok:
            flags.append("ckpt-corrupt")
        if not r.provider_parse_succeeded:
            flags.append("parse-fail")
        if r.malformed_patch_recovered:
            flags.append("recovered")
        if r.unauthorized_mutations > 0:
            flags.append(f"mutations={r.unauthorized_mutations}")
        flag_str = f"  [{','.join(flags)}]" if flags else ""
        lines.append(
            f"[{status}] {r.fixture_name}  "
            f"turns={r.turns_used}  "
            f"tools={r.tool_calls}  "
            f"redundant_reads={r.redundant_reads}  "
            f"tokens={r.input_tokens+r.output_tokens}  "
            f"time={r.wall_seconds:.1f}s"
            f"{flag_str}"
        )
        if r.error:
            category = f"  [{r.failure_category}]" if r.failure_category else ""
            lines.append(f"       error{category}: {r.error}")
    return "\n".join(lines)


def render_repeated_summary(summary: LiveRepeatedSummary) -> str:
    lines = ["SafeCode Live Eval Repeated Summary", "=" * 40]
    lines.append(f"Overall pass rate: {summary.overall_pass_rate:.3f}")
    lines.append("")
    for item in summary.fixtures:
        lines.append(
            f"{item.fixture_name}: "
            f"pass@1={item.pass_at_1:.3f} "
            f"pass@N={item.pass_at_n:.3f} "
            f"pass={item.pass_rate:.3f} "
            f"retry={item.retry_rate:.3f} "
            f"repair={item.repair_rate:.3f} "
            f"recovery={item.recovery_rate:.3f} "
            f"avg_tokens={item.avg_tokens:.1f} "
            f"p95_tokens={item.p95_tokens:.1f} "
            f"avg_time={item.avg_wall_seconds:.1f}s "
            f"p95_time={item.p95_wall_seconds:.1f}s "
            f"safety={'ok' if item.safety_invariants_ok else 'broken'}"
        )
    return "\n".join(lines)
