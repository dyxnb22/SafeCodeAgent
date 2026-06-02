"""Tests for the v2.8.1 internal diagnostic migration.

These tests assert that doctor/release/policy emit typed Diagnostic objects
internally while preserving the legacy public surfaces.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.core.diagnostic import (
    Diagnostic,
    DiagnosticStatus,
    aggregate_status,
    all_passed,
)
from safecode.doctor import Doctor, DoctorCheck
from safecode.policy.audit import audit_policy
from safecode.release.check import ReleaseCheckResult, run_release_check
from safecode.release.preflight import run_release_preflight
from safecode.release.signoff import run_release_signoff
from safecode.release.smoke import (
    SmokeTestCase,
    collect_smoke_diagnostics,
    run_smoke_tests,
)


# ---------- Doctor ----------


class TestDoctorDiagnostics:
    def test_run_diagnostics_returns_diagnostic_list(self, tmp_path: Path) -> None:
        diagnostics = Doctor(tmp_path).run_diagnostics()
        assert all(isinstance(d, Diagnostic) for d in diagnostics)
        # Same set of core check names as legacy.
        names = {d.name for d in diagnostics}
        for required in (
            "python",
            "uv",
            "project_root",
            "pyproject",
            "config",
            "sac_dir",
            "approval_dir",
            "sandbox_approval_dir",
        ):
            assert required in names

    def test_run_diagnostics_release_mode_adds_release_diagnostics(
        self, tmp_path: Path
    ) -> None:
        diagnostics = Doctor(tmp_path).run_diagnostics(release=True)
        names = {d.name for d in diagnostics}
        assert "release_version" in names
        assert "release_tag" in names
        assert "release_docs" in names
        assert "release_preflight" in names

    def test_legacy_run_still_returns_doctor_checks(self, tmp_path: Path) -> None:
        checks = Doctor(tmp_path).run()
        assert all(isinstance(c, DoctorCheck) for c in checks)

    def test_doctor_check_to_diagnostic_round_trip(self) -> None:
        check = DoctorCheck(name="python", passed=True, detail="3.13.0")
        diag = check.to_diagnostic()
        assert diag.name == "python"
        assert diag.status is DiagnosticStatus.PASS
        assert diag.message == "3.13.0"

    def test_doctor_check_failure_maps_to_fail(self) -> None:
        check = DoctorCheck(name="uv", passed=False, detail="not found")
        diag = check.to_diagnostic()
        assert diag.status is DiagnosticStatus.FAIL


# ---------- release/check ----------


class TestReleaseCheckDiagnostics:
    def _write_pyproject(self, tmp_path: Path, version: str) -> Path:
        p = tmp_path / "pyproject.toml"
        p.write_text(
            f'[project]\nname = "safecode-agent"\nversion = "{version}"\n',
            encoding="utf-8",
        )
        return p

    def test_to_diagnostics_returns_typed_list(self, tmp_path: Path) -> None:
        pyproject = self._write_pyproject(tmp_path, "2.6.1")
        result: ReleaseCheckResult = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.1",
        )
        diagnostics = result.to_diagnostics()
        assert all(isinstance(d, Diagnostic) for d in diagnostics)
        names = [d.name for d in diagnostics]
        assert "release_check_version" in names
        assert "release_check_tree" in names

    def test_unknown_git_tree_becomes_skip(self, tmp_path: Path) -> None:
        pyproject = self._write_pyproject(tmp_path, "2.6.1")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.1",
            git_tag=None,
        )
        # tmp_path is not a git checkout, so tree_clean is None → SKIP.
        diagnostics = {d.name: d for d in result.to_diagnostics()}
        assert diagnostics["release_check_tree"].status is DiagnosticStatus.SKIP

    def test_mismatched_version_emits_fail(self, tmp_path: Path) -> None:
        pyproject = self._write_pyproject(tmp_path, "2.5.0")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.1",
        )
        diagnostics = {d.name: d for d in result.to_diagnostics()}
        assert diagnostics["release_check_version"].status is DiagnosticStatus.FAIL


# ---------- release/smoke ----------


class TestReleaseSmokeDiagnostics:
    def test_collect_smoke_diagnostics_typed(self) -> None:
        diagnostics = collect_smoke_diagnostics()
        assert all(isinstance(d, Diagnostic) for d in diagnostics)
        names = {d.name for d in diagnostics}
        assert "import_version" in names
        assert "cli_version" in names
        assert "version_consistency" in names
        assert "policy_names" in names
        assert "docs_finalized" in names

    def test_run_smoke_tests_to_diagnostics(self) -> None:
        result = run_smoke_tests()
        typed = result.to_diagnostics()
        assert len(typed) == len(result.cases)
        assert all(isinstance(d, Diagnostic) for d in typed)

    def test_smoke_test_case_to_diagnostic(self) -> None:
        case = SmokeTestCase(name="x", passed=True, detail="ok")
        diag = case.to_diagnostic()
        assert diag.status is DiagnosticStatus.PASS
        assert diag.name == "x"
        assert diag.message == "ok"


# ---------- release/preflight ----------


class TestPreflightDiagnostics:
    def test_to_diagnostics_returns_component_view(self, tmp_path: Path) -> None:
        result = run_release_preflight(tmp_path)
        diagnostics = result.to_diagnostics()
        assert all(isinstance(d, Diagnostic) for d in diagnostics)
        names = {d.name for d in diagnostics}
        for required in ("release_check", "smoke", "metadata", "docs"):
            assert required in names

    def test_to_diagnostics_aggregate_matches_ok(self, tmp_path: Path) -> None:
        result = run_release_preflight(tmp_path)
        diagnostics = result.to_diagnostics()
        if not result.ok:
            assert aggregate_status(diagnostics) is DiagnosticStatus.FAIL
            assert all_passed(diagnostics) is False


# ---------- release/signoff ----------


class TestSignoffDiagnostics:
    def test_to_diagnostics_lists_three_components(self, tmp_path: Path) -> None:
        result = run_release_signoff(tmp_path)
        diagnostics = result.to_diagnostics()
        names = {d.name for d in diagnostics}
        assert names == {
            "signoff_exact_tag",
            "signoff_release_check",
            "signoff_preflight",
        }


# ---------- policy/audit ----------


class TestPolicyAuditDiagnostics:
    def test_audit_policy_to_diagnostics(self, tmp_path: Path) -> None:
        # No env policy, no project config → audit should pass.
        result = audit_policy(tmp_path, env_policy=None)
        diagnostics = result.to_diagnostics()
        names = [d.name for d in diagnostics]
        for required in (
            "policy_known_names",
            "policy_aliases",
            "policy_preset_invariants",
            "policy_audit",
        ):
            assert required in names

    def test_unknown_env_policy_marks_failure(self, tmp_path: Path) -> None:
        result = audit_policy(tmp_path, env_policy="bogus-policy")
        diagnostics = {d.name: d for d in result.to_diagnostics()}
        # policy_audit aggregates failures so it must reflect them.
        assert diagnostics["policy_audit"].status is DiagnosticStatus.FAIL


# ---------- Aggregation across substrates ----------


class TestCrossSubstrateAggregation:
    def test_failing_diagnostic_dominates_aggregate(self) -> None:
        diagnostics = [
            Diagnostic(name="ok", status=DiagnosticStatus.PASS),
            Diagnostic(name="warn", status=DiagnosticStatus.WARN),
            Diagnostic(name="bad", status=DiagnosticStatus.FAIL),
        ]
        assert aggregate_status(diagnostics) is DiagnosticStatus.FAIL
        assert all_passed(diagnostics) is False

    def test_skip_does_not_count_as_fail(self) -> None:
        diagnostics = [
            Diagnostic(name="a", status=DiagnosticStatus.PASS),
            Diagnostic(name="b", status=DiagnosticStatus.SKIP),
        ]
        # SKIP is not a pass, but not a fail either.
        assert aggregate_status(diagnostics) is DiagnosticStatus.SKIP
        assert all_passed(diagnostics) is False
