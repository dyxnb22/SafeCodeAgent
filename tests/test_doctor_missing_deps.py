"""Tests for sac doctor project tooling group (v4.2.2 T-4.2.2-A)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.core.diagnostic import DiagnosticStatus
from safecode.doctor import Doctor
from safecode.project.profile import (
    ProfileCommand,
    ProjectProfile,
    save_profile,
)

runner = CliRunner(mix_stderr=False)


def _cmd(argv: tuple[str, ...], missing: bool = False) -> ProfileCommand:
    return ProfileCommand(command=argv, stack="test", source="detected", missing_dependency=missing)


class TestProjectToolingDiagnosticsNoProfile:
    def test_no_profile_returns_single_skip(self, tmp_path):
        doc = Doctor(tmp_path, fetch_latest_version=lambda: None)
        diags = doc._project_tooling_diagnostics()
        assert len(diags) == 1
        assert diags[0].status == DiagnosticStatus.SKIP
        assert "profile detect" in diags[0].message

    def test_no_profile_name_is_project_tooling(self, tmp_path):
        doc = Doctor(tmp_path, fetch_latest_version=lambda: None)
        diags = doc._project_tooling_diagnostics()
        assert diags[0].name == "project_tooling"


class TestProjectToolingDiagnosticsPass:
    def test_detected_command_with_tool_present_is_pass(self, tmp_path):
        profile = ProjectProfile(test=_cmd(("echo", "hi"), missing=False))
        save_profile(tmp_path, profile)
        doc = Doctor(tmp_path, fetch_latest_version=lambda: None)
        diags = doc._project_tooling_diagnostics()
        test_diag = next(d for d in diags if d.name == "project_tooling_test")
        assert test_diag.status == DiagnosticStatus.PASS
        assert "echo hi" in test_diag.message

    def test_all_four_kinds_with_tools_present(self, tmp_path):
        profile = ProjectProfile(
            test=_cmd(("echo", "test")),
            lint=_cmd(("echo", "lint")),
            typecheck=_cmd(("echo", "typecheck")),
            build=_cmd(("echo", "build")),
        )
        save_profile(tmp_path, profile)
        doc = Doctor(tmp_path, fetch_latest_version=lambda: None)
        diags = doc._project_tooling_diagnostics()
        names = {d.name for d in diags}
        assert "project_tooling_test" in names
        assert "project_tooling_lint" in names
        assert "project_tooling_typecheck" in names
        assert "project_tooling_build" in names
        for d in diags:
            assert d.status == DiagnosticStatus.PASS


class TestProjectToolingDiagnosticsSkip:
    def test_missing_tool_is_skip_not_fail(self, tmp_path):
        """CRITICAL: missing_dependency=True must map to SKIP, never FAIL."""
        profile = ProjectProfile(test=_cmd(("mypy", "."), missing=True))
        save_profile(tmp_path, profile)
        doc = Doctor(tmp_path, fetch_latest_version=lambda: None)
        diags = doc._project_tooling_diagnostics()
        test_diag = next(d for d in diags if d.name == "project_tooling_test")
        assert test_diag.status == DiagnosticStatus.SKIP
        assert test_diag.status != DiagnosticStatus.FAIL

    def test_not_detected_is_skip(self, tmp_path):
        """When a kind is not in the profile (None), it should be SKIP."""
        profile = ProjectProfile(test=_cmd(("pytest", "-q")))  # no lint/typecheck/build
        save_profile(tmp_path, profile)
        doc = Doctor(tmp_path, fetch_latest_version=lambda: None)
        diags = doc._project_tooling_diagnostics()
        lint_diag = next(d for d in diags if d.name == "project_tooling_lint")
        assert lint_diag.status == DiagnosticStatus.SKIP
        assert "not detected" in lint_diag.message

    def test_missing_tool_message_includes_binary(self, tmp_path):
        """SKIP message for missing tool must include the binary name."""
        profile = ProjectProfile(lint=_cmd(("ruff", "check", "."), missing=True))
        save_profile(tmp_path, profile)
        doc = Doctor(tmp_path, fetch_latest_version=lambda: None)
        diags = doc._project_tooling_diagnostics()
        lint_diag = next(d for d in diags if d.name == "project_tooling_lint")
        assert "ruff" in lint_diag.message

    def test_missing_tool_message_includes_profile_set_hint(self, tmp_path):
        """SKIP message should hint at sac profile set."""
        profile = ProjectProfile(typecheck=_cmd(("mypy", "."), missing=True))
        save_profile(tmp_path, profile)
        doc = Doctor(tmp_path, fetch_latest_version=lambda: None)
        diags = doc._project_tooling_diagnostics()
        tc_diag = next(d for d in diags if d.name == "project_tooling_typecheck")
        assert "profile set" in tc_diag.message


class TestProjectToolingMixedStates:
    def test_mixed_pass_skip(self, tmp_path):
        """Some kinds pass, some are missing, some not detected."""
        profile = ProjectProfile(
            test=_cmd(("echo", "test")),         # PASS (echo always present)
            lint=_cmd(("ruff", "check", "."), missing=True),  # SKIP (missing)
            typecheck=None,                       # SKIP (not detected)
            build=None,                           # SKIP (not detected)
        )
        save_profile(tmp_path, profile)
        doc = Doctor(tmp_path, fetch_latest_version=lambda: None)
        diags = doc._project_tooling_diagnostics()
        by_name = {d.name: d for d in diags}
        assert by_name["project_tooling_test"].status == DiagnosticStatus.PASS
        assert by_name["project_tooling_lint"].status == DiagnosticStatus.SKIP
        assert by_name["project_tooling_typecheck"].status == DiagnosticStatus.SKIP
        assert by_name["project_tooling_build"].status == DiagnosticStatus.SKIP


class TestProjectToolingInRunDiagnostics:
    def test_tooling_diagnostics_in_run_diagnostics(self, tmp_path):
        """project_tooling_* diagnostics appear in Doctor.run_diagnostics()."""
        (tmp_path / "Cargo.toml").touch()
        profile = ProjectProfile(test=_cmd(("echo", "test")))
        save_profile(tmp_path, profile)
        doc = Doctor(tmp_path, fetch_latest_version=lambda: None)
        all_diags = doc.run_diagnostics()
        names = [d.name for d in all_diags]
        assert any(n.startswith("project_tooling") for n in names)

    def test_no_profile_single_skip_in_run_diagnostics(self, tmp_path):
        """Without a profile, only 'project_tooling' (singular) appears."""
        doc = Doctor(tmp_path, fetch_latest_version=lambda: None)
        all_diags = doc.run_diagnostics()
        tooling_diags = [d for d in all_diags if d.name.startswith("project_tooling")]
        assert len(tooling_diags) == 1
        assert tooling_diags[0].status == DiagnosticStatus.SKIP

    def test_diagnostic_substrate_contract_preserved(self, tmp_path):
        """Each diagnostic has name, status, message fields."""
        doc = Doctor(tmp_path, fetch_latest_version=lambda: None)
        diags = doc.run_diagnostics()
        for d in diags:
            assert hasattr(d, "name")
            assert hasattr(d, "status")
            assert hasattr(d, "message")
            assert d.status in (
                DiagnosticStatus.PASS,
                DiagnosticStatus.FAIL,
                DiagnosticStatus.WARN,
                DiagnosticStatus.SKIP,
            )


class TestDoctorCLIIntegration:
    def _invoke(self, cwd: Path):
        import os
        old = os.getcwd()
        try:
            os.chdir(cwd)
            return runner.invoke(app, ["doctor"])
        finally:
            os.chdir(old)

    def test_doctor_shows_profile_tooling(self, tmp_path):
        profile = ProjectProfile(test=_cmd(("echo", "test")))
        save_profile(tmp_path, profile)
        result = self._invoke(tmp_path)
        assert result.exit_code == 0

    def test_doctor_shows_skip_when_no_profile(self, tmp_path):
        result = self._invoke(tmp_path)
        # Doctor should complete without crash even with no profile
        assert result.exit_code == 0
