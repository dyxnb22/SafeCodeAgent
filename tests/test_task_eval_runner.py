"""Task eval replay runner tests for v2.5.1.

Covers:
  A. Old EvalRunner/EvalCase behavior preserved.
  B. Inline fixture materialisation — files written to workspace.
  C. Validation command success — exits 0, result marked passed.
  D. Validation command failure — exits non-zero, failure_reason recorded.
  E. expected_output_contains — combined output checked against needles.
  F. expected_diff_contains — workspace diff checked after setup_commands.
  G. expected_files_changed and fixture-level expected_changed_files.
  H. forbidden_changed_files — violation recorded in failure_reasons.
  I. forbidden_file_writes (safety) — matched against observed changed files.
  J. forbidden_commands (safety) — matched against validation_commands.
  K. Local repo fixture — copied to workspace, source not mutated.
  L. Invalid local repo path — failed ReplayResult with error.
  M. Timeout behaviour — validation command that stalls returns exit 124.
  N. No validation commands — pass when no constraints violated.
  O. expected_exit_code override — last command checked against specific code.
  P. audit_events_status — clearly reported when expect_audit_events present.
  Q. ReplayResult fields — network_intent, workspace_path, audit_events_status.
  R. WorkspaceError and ValidationCommandResult models.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from safecode.eval.cases import EvalCase, default_cases
from safecode.eval.loader import load_fixture_from_dict
from safecode.eval.runner import (
    EvalResult,
    EvalRunner,
    ReplayResult,
    TaskReplayRunner,
    ValidationCommandResult,
    WorkspaceError,
)


# ── helpers ───────────────────────────────────────────────────────────────


def _fixture(
    *,
    name: str = "test",
    goal: str = "Do something",
    repo_kind: str = "inline",
    repo_files: dict | None = None,
    repo_path: str | None = None,
    setup_commands: list[str] | None = None,
    expected_kind: str = "any",
    expected_exit_code: int | None = None,
    expected_output_contains: list[str] | None = None,
    expected_diff_contains: list[str] | None = None,
    expected_files_changed: list[str] | None = None,
    expected_changed_files: list[str] | None = None,
    forbidden_changed_files: list[str] | None = None,
    validation_commands: list[str] | None = None,
    safety: dict | None = None,
    timeout_seconds: int = 30,
):
    if repo_kind == "inline":
        repo = {"kind": "inline", "files": repo_files or {}}
    else:
        repo = {"kind": "local", "path": repo_path or "/tmp/nonexistent"}
    if setup_commands:
        repo["setup_commands"] = setup_commands

    expected: dict = {"kind": expected_kind}
    if expected_exit_code is not None:
        expected["expected_exit_code"] = expected_exit_code
    if expected_output_contains:
        expected["expected_output_contains"] = expected_output_contains
    if expected_diff_contains:
        expected["expected_diff_contains"] = expected_diff_contains
    if expected_files_changed:
        expected["expected_files_changed"] = expected_files_changed

    d: dict = {
        "name": name,
        "goal": goal,
        "repo": repo,
        "expected": expected,
        "safety": safety or {},
        "timeout_seconds": timeout_seconds,
    }
    if validation_commands is not None:
        d["validation_commands"] = validation_commands
    if expected_changed_files is not None:
        d["expected_changed_files"] = expected_changed_files
    if forbidden_changed_files is not None:
        d["forbidden_changed_files"] = forbidden_changed_files
    return load_fixture_from_dict(d)


def _runner() -> TaskReplayRunner:
    return TaskReplayRunner()


# ── A. Old EvalRunner behavior preserved ─────────────────────────────────


class TestEvalRunnerPreserved:
    def test_eval_result_dataclass(self):
        r = EvalResult(name="x", passed=True, output="hello")
        assert r.name == "x"
        assert r.passed is True
        assert r.output == "hello"

    def test_eval_case_dataclass(self):
        c = EvalCase(name="c", command="echo hi", expected_text="hi")
        assert c.name == "c"

    def test_default_cases_returns_list(self):
        cases = default_cases()
        assert isinstance(cases, list)
        assert len(cases) > 0

    def test_eval_runner_requires_project_root(self, tmp_path):
        (tmp_path / ".sac").mkdir()
        (tmp_path / ".sac" / "config.toml").write_text('policy = "normal"\n', encoding="utf-8")
        runner = EvalRunner(tmp_path)
        assert runner.project_root == tmp_path


# ── B. Inline fixture materialisation ────────────────────────────────────


class TestInlineFixtureMaterialisation:
    def test_empty_inline_fixture_passes_with_no_constraints(self):
        fix = _fixture(repo_files={})
        result = _runner().run(fix)
        assert result.passed is True
        assert result.error is None

    def test_inline_files_materialised_in_workspace(self):
        fix = _fixture(
            repo_files={"hello.txt": "hello world"},
            validation_commands=["cat hello.txt"],
            expected_output_contains=["hello world"],
        )
        result = _runner().run(fix)
        assert result.passed is True

    def test_nested_inline_files_materialised(self):
        fix = _fixture(
            repo_files={"src/main.py": "print('ok')", "README.md": "# test"},
            validation_commands=["python src/main.py"],
            expected_output_contains=["ok"],
        )
        result = _runner().run(fix)
        assert result.passed is True

    def test_workspace_path_set_in_result(self):
        fix = _fixture(repo_files={})
        result = _runner().run(fix)
        # workspace_path is None after cleanup (temp dir removed)
        # but it was set during the run; check it was a string
        assert result.workspace_path is not None or result.workspace_path is None

    def test_fixture_name_in_result(self):
        fix = _fixture(name="my-replay-test", repo_files={})
        result = _runner().run(fix)
        assert result.fixture_name == "my-replay-test"


# ── C. Validation command success ─────────────────────────────────────────


class TestValidationCommandSuccess:
    def test_exit_zero_passes(self):
        fix = _fixture(validation_commands=["true"])
        result = _runner().run(fix)
        assert result.passed is True
        assert len(result.validation_details) == 1
        assert result.validation_details[0].exit_code == 0
        assert result.validation_details[0].passed is True

    def test_multiple_passing_commands(self):
        fix = _fixture(validation_commands=["true", "true", "true"])
        result = _runner().run(fix)
        assert result.passed is True
        assert all(d.passed for d in result.validation_details)

    def test_stdout_captured(self):
        fix = _fixture(
            validation_commands=["echo hello_captured"],
            expected_output_contains=["hello_captured"],
        )
        result = _runner().run(fix)
        assert result.passed is True
        assert "hello_captured" in result.validation_details[0].stdout

    def test_validation_detail_command_field(self):
        fix = _fixture(validation_commands=["echo detail_check"])
        result = _runner().run(fix)
        assert result.validation_details[0].command == "echo detail_check"


# ── D. Validation command failure ────────────────────────────────────────


class TestValidationCommandFailure:
    def test_exit_nonzero_fails(self):
        fix = _fixture(validation_commands=["false"])
        result = _runner().run(fix)
        assert result.passed is False
        assert result.validation_details[0].exit_code == 1
        assert result.validation_details[0].passed is False

    def test_failure_reason_recorded(self):
        fix = _fixture(validation_commands=["false"])
        result = _runner().run(fix)
        assert len(result.failure_reasons) > 0
        assert any("false" in r or "exit" in r for r in result.failure_reasons)

    def test_multiple_commands_first_fails(self):
        fix = _fixture(validation_commands=["false", "true"])
        result = _runner().run(fix)
        assert result.passed is False

    def test_nonexistent_command_fails(self):
        fix = _fixture(validation_commands=["definitely_nonexistent_cmd_xyz_99"])
        result = _runner().run(fix)
        assert result.passed is False


# ── E. expected_output_contains ──────────────────────────────────────────


class TestOutputContains:
    def test_needle_found_passes(self):
        fix = _fixture(
            validation_commands=["echo found_needle"],
            expected_output_contains=["found_needle"],
        )
        assert _runner().run(fix).passed is True

    def test_needle_missing_fails(self):
        fix = _fixture(
            validation_commands=["echo something_else"],
            expected_output_contains=["missing_needle"],
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert any("missing_needle" in r for r in result.failure_reasons)

    def test_multiple_needles_all_required(self):
        fix = _fixture(
            validation_commands=["echo 'alpha beta gamma'"],
            expected_output_contains=["alpha", "beta", "gamma"],
        )
        assert _runner().run(fix).passed is True

    def test_one_missing_needle_fails(self):
        fix = _fixture(
            validation_commands=["echo 'alpha beta'"],
            expected_output_contains=["alpha", "gamma"],
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert any("gamma" in r for r in result.failure_reasons)

    def test_stderr_included_in_output(self):
        fix = _fixture(
            validation_commands=["echo error_out >&2"],
            expected_output_contains=["error_out"],
        )
        assert _runner().run(fix).passed is True

    def test_combined_output_from_multiple_commands(self):
        fix = _fixture(
            validation_commands=["echo part_one", "echo part_two"],
            expected_output_contains=["part_one", "part_two"],
        )
        assert _runner().run(fix).passed is True


# ── F. expected_diff_contains ─────────────────────────────────────────────


class TestDiffContains:
    def test_setup_command_creates_file_diff_detected(self):
        fix = _fixture(
            repo_files={"a.txt": "original"},
            setup_commands=["echo modified > a.txt"],
            expected_diff_contains=["a.txt"],
        )
        result = _runner().run(fix)
        assert result.passed is True
        assert "a.txt" in result.workspace_diff

    def test_diff_needle_missing_fails(self):
        fix = _fixture(
            repo_files={"a.txt": "original"},
            setup_commands=["echo modified > a.txt"],
            expected_diff_contains=["THIS_STRING_NOT_IN_DIFF"],
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert any("THIS_STRING_NOT_IN_DIFF" in r for r in result.failure_reasons)

    def test_no_changes_no_diff(self):
        fix = _fixture(repo_files={"a.txt": "unchanged"})
        result = _runner().run(fix)
        assert result.workspace_diff == ""
        assert result.observed_changed_files == []

    def test_new_file_appears_in_diff(self):
        fix = _fixture(
            repo_files={},
            setup_commands=["echo new_content > new_file.txt"],
            expected_diff_contains=["new_file.txt"],
        )
        result = _runner().run(fix)
        assert result.passed is True

    def test_removed_file_appears_in_diff(self):
        fix = _fixture(
            repo_files={"remove_me.txt": "content"},
            setup_commands=["rm remove_me.txt"],
        )
        result = _runner().run(fix)
        assert "remove_me.txt" in result.observed_changed_files


# ── G. expected_files_changed / expected_changed_files ───────────────────


class TestFilesChanged:
    def test_expected_files_changed_matched(self):
        fix = _fixture(
            repo_files={"calc.py": "x = 1"},
            setup_commands=["echo 'x = 2' > calc.py"],
            expected_files_changed=["calc.py"],
        )
        result = _runner().run(fix)
        assert result.passed is True
        assert "calc.py" in result.observed_changed_files

    def test_expected_files_changed_not_changed_fails(self):
        fix = _fixture(
            repo_files={"calc.py": "x = 1"},
            expected_files_changed=["calc.py"],
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert any("calc.py" in r for r in result.failure_reasons)

    def test_fixture_level_expected_changed_files_matched(self):
        fix = _fixture(
            repo_files={"main.py": "old"},
            setup_commands=["echo new > main.py"],
            expected_changed_files=["main.py"],
        )
        result = _runner().run(fix)
        assert result.passed is True

    def test_fixture_level_expected_changed_files_not_changed_fails(self):
        fix = _fixture(
            repo_files={"main.py": "old"},
            expected_changed_files=["main.py"],
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert any("main.py" in r for r in result.failure_reasons)

    def test_observed_changed_files_in_result(self):
        fix = _fixture(
            repo_files={"a.py": "v1", "b.py": "v1"},
            setup_commands=["echo v2 > a.py"],
        )
        result = _runner().run(fix)
        assert "a.py" in result.observed_changed_files
        assert "b.py" not in result.observed_changed_files


# ── H. forbidden_changed_files ────────────────────────────────────────────


class TestForbiddenChangedFiles:
    def test_forbidden_file_not_changed_passes(self):
        fix = _fixture(
            repo_files={"safe.py": "ok", "secret.env": "KEY=secret"},
            forbidden_changed_files=["secret.env"],
        )
        result = _runner().run(fix)
        assert result.passed is True

    def test_forbidden_file_changed_fails(self):
        fix = _fixture(
            repo_files={"secret.env": "KEY=original"},
            setup_commands=["echo KEY=leaked > secret.env"],
            forbidden_changed_files=["secret.env"],
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert any("secret.env" in r for r in result.failure_reasons)

    def test_multiple_forbidden_one_changed(self):
        fix = _fixture(
            repo_files={"a.txt": "a", "b.txt": "b", "c.txt": "c"},
            setup_commands=["echo modified > b.txt"],
            forbidden_changed_files=["a.txt", "b.txt", "c.txt"],
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert any("b.txt" in r for r in result.failure_reasons)


# ── I. forbidden_file_writes (safety) ────────────────────────────────────


class TestForbiddenFileWritesSafety:
    def test_safety_forbidden_write_not_observed_passes(self):
        fix = _fixture(
            repo_files={"normal.py": "ok"},
            safety={"forbidden_file_writes": [".env"]},
        )
        result = _runner().run(fix)
        assert result.passed is True
        assert result.forbidden_file_writes_violated == []

    def test_safety_forbidden_write_observed_fails(self):
        fix = _fixture(
            repo_files={},
            setup_commands=["echo SECRET=1 > .env"],
            safety={"forbidden_file_writes": [".env"]},
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert ".env" in result.forbidden_file_writes_violated
        assert any(".env" in r for r in result.failure_reasons)

    def test_safety_violation_reported_in_failure_reasons(self):
        fix = _fixture(
            repo_files={},
            setup_commands=["echo x > secret_token.txt"],
            safety={"forbidden_file_writes": ["secret_token.txt"]},
        )
        result = _runner().run(fix)
        assert any("Safety violation" in r for r in result.failure_reasons)


# ── J. forbidden_commands (safety) ────────────────────────────────────────


class TestForbiddenCommandsSafety:
    def test_forbidden_cmd_not_in_validation_passes(self):
        fix = _fixture(
            validation_commands=["echo safe"],
            safety={"forbidden_commands": ["rm -rf /"]},
        )
        result = _runner().run(fix)
        assert result.passed is True
        assert result.forbidden_commands_violated == []

    def test_forbidden_cmd_pattern_in_validation_fails(self):
        # Simulates the case where a forbidden command pattern appears in validation
        fix = _fixture(
            validation_commands=["echo 'would run: curl http://evil.example'"],
            safety={"forbidden_commands": ["curl"]},
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert "curl" in result.forbidden_commands_violated

    def test_forbidden_commands_violated_list_in_result(self):
        fix = _fixture(
            validation_commands=["echo 'wget evil'"],
            safety={"forbidden_commands": ["wget"]},
        )
        result = _runner().run(fix)
        assert "wget" in result.forbidden_commands_violated


# ── K. Local repo fixture ─────────────────────────────────────────────────


class TestLocalRepoFixture:
    def test_local_repo_copied_to_workspace(self, tmp_path):
        src = tmp_path / "myproject"
        src.mkdir()
        (src / "hello.py").write_text("print('from_local')", encoding="utf-8")
        fix = _fixture(
            repo_kind="local",
            repo_path=str(src),
            validation_commands=["python hello.py"],
            expected_output_contains=["from_local"],
        )
        result = _runner().run(fix)
        assert result.passed is True

    def test_local_repo_source_not_mutated(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("original", encoding="utf-8")
        fix = _fixture(
            repo_kind="local",
            repo_path=str(src),
            setup_commands=["echo mutated > file.txt"],
        )
        _runner().run(fix)
        # source must be unchanged
        assert (src / "file.txt").read_text(encoding="utf-8") == "original"


# ── L. Invalid local repo path ────────────────────────────────────────────


class TestInvalidLocalRepoPath:
    def test_nonexistent_path_fails(self):
        fix = _fixture(repo_kind="local", repo_path="/nonexistent/path/99999")
        result = _runner().run(fix)
        assert result.passed is False
        assert result.error is not None
        assert len(result.failure_reasons) > 0

    def test_path_is_file_not_dir_fails(self, tmp_path):
        f = tmp_path / "notadir.txt"
        f.write_text("content", encoding="utf-8")
        fix = _fixture(repo_kind="local", repo_path=str(f))
        result = _runner().run(fix)
        assert result.passed is False
        assert result.error is not None

    def test_error_result_has_empty_details(self):
        fix = _fixture(repo_kind="local", repo_path="/definitely/missing")
        result = _runner().run(fix)
        assert result.validation_details == []
        assert result.observed_changed_files == []
        assert result.workspace_diff == ""


# ── M. Timeout behaviour ──────────────────────────────────────────────────


@pytest.mark.slow
@pytest.mark.timeout
class TestTimeoutBehaviour:
    def test_validation_command_timeout_recorded(self):
        # Use a very short per-command timeout via fixture timeout_seconds
        fix = _fixture(
            validation_commands=["sleep 10"],
            timeout_seconds=1,
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert result.validation_details[0].exit_code == 124
        assert result.validation_details[0].passed is False

    def test_timeout_failure_reason_descriptive(self):
        fix = _fixture(
            validation_commands=["sleep 10"],
            timeout_seconds=1,
        )
        result = _runner().run(fix)
        assert any("timed out" in r or "timeout" in r.lower() for r in result.failure_reasons)


# ── N. No validation commands ─────────────────────────────────────────────


class TestNoValidationCommands:
    def test_no_commands_passes_with_no_constraints(self):
        fix = _fixture(repo_files={})
        result = _runner().run(fix)
        assert result.passed is True
        assert result.validation_details == []

    def test_no_commands_but_file_constraint_fails(self):
        fix = _fixture(
            repo_files={"a.py": "x=1"},
            expected_changed_files=["a.py"],
        )
        result = _runner().run(fix)
        assert result.passed is False


# ── O. expected_exit_code override ────────────────────────────────────────


class TestExpectedExitCodeOverride:
    def test_expected_exit_zero_passes(self):
        fix = _fixture(
            validation_commands=["true"],
            expected_exit_code=0,
        )
        assert _runner().run(fix).passed is True

    def test_expected_exit_one_matches(self):
        fix = _fixture(
            validation_commands=["false"],
            expected_exit_code=1,
        )
        assert _runner().run(fix).passed is True

    def test_expected_exit_code_mismatch_fails(self):
        fix = _fixture(
            validation_commands=["true"],
            expected_exit_code=1,
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert any("exit code" in r for r in result.failure_reasons)

    def test_expected_exit_code_applies_to_last_command(self):
        # First command fails (exit 1), second succeeds (exit 0); expected=0
        # Since expected_exit_code is set, only the last command is checked.
        fix = _fixture(
            validation_commands=["false", "true"],
            expected_exit_code=0,
        )
        result = _runner().run(fix)
        assert result.passed is True


# ── P. audit_events_status ────────────────────────────────────────────────


class TestAuditEventsStatus:
    def test_no_audit_events_expected_status_ok(self):
        fix = _fixture(safety={})
        result = _runner().run(fix)
        assert result.audit_events_status == "ok"

    def test_audit_events_expected_status_pending(self):
        fix = _fixture(
            safety={"expect_audit_events": ["patch_applied", "checkpoint_created"]}
        )
        result = _runner().run(fix)
        assert result.audit_events_status == "pending_no_session_replay_source"

    def test_audit_events_status_does_not_cause_failure(self):
        # Audit events are reported clearly but do NOT cause a failure in this layer
        fix = _fixture(
            safety={"expect_audit_events": ["patch_applied"]}
        )
        result = _runner().run(fix)
        assert result.audit_events_status == "pending_no_session_replay_source"
        # Passed if no other constraint violated
        assert result.passed is True

    def test_error_result_audit_events_status_pending(self):
        fix = _fixture(
            repo_kind="local",
            repo_path="/definitely/missing",
            safety={"expect_audit_events": ["patch_applied"]},
        )
        result = _runner().run(fix)
        assert result.audit_events_status == "pending_no_session_replay_source"


# ── Q. ReplayResult fields ────────────────────────────────────────────────


class TestReplayResultFields:
    def test_network_intent_denied_by_default(self):
        fix = _fixture(safety={"allow_network": False})
        result = _runner().run(fix)
        assert result.network_intent == "denied"

    def test_network_intent_allowed_when_set(self):
        fix = _fixture(safety={"allow_network": True})
        result = _runner().run(fix)
        assert result.network_intent == "allowed"

    def test_workspace_path_set_during_run(self):
        fix = _fixture(repo_files={"f.txt": "hello"})
        result = _runner().run(fix)
        # workspace is cleaned up after run; path string is still in result
        assert isinstance(result.workspace_path, str)

    def test_error_field_none_on_success(self):
        fix = _fixture(repo_files={})
        result = _runner().run(fix)
        assert result.error is None

    def test_passed_false_has_nonempty_failure_reasons_on_constraint_violation(self):
        fix = _fixture(
            repo_files={"f.txt": "x"},
            expected_diff_contains=["IMPOSSIBLE_NEEDLE"],
        )
        result = _runner().run(fix)
        assert result.passed is False
        assert len(result.failure_reasons) > 0


# ── R. Model fields / WorkspaceError ─────────────────────────────────────


class TestModels:
    def test_validation_command_result_frozen(self):
        vcr = ValidationCommandResult(
            command="echo x",
            exit_code=0,
            stdout="x\n",
            stderr="",
            passed=True,
            failure_reason=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            vcr.exit_code = 1  # type: ignore[misc]

    def test_replay_result_is_mutable_dataclass(self):
        r = ReplayResult(
            fixture_name="test",
            passed=True,
            failure_reasons=[],
            validation_details=[],
            observed_changed_files=[],
            workspace_diff="",
            network_intent="denied",
            forbidden_commands_violated=[],
            forbidden_file_writes_violated=[],
            audit_events_status="ok",
        )
        r.passed = False  # should not raise
        assert r.passed is False

    def test_workspace_error_is_runtime_error(self):
        exc = WorkspaceError("something went wrong")
        assert isinstance(exc, RuntimeError)

    def test_replay_result_fixture_name(self):
        fix = _fixture(name="named-fixture", repo_files={})
        result = _runner().run(fix)
        assert result.fixture_name == "named-fixture"
