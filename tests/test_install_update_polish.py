from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode import __version__
from safecode.cli import app
from safecode.doctor import Doctor
from safecode.release.version_guard import check_version_consistency


def test_package_version_is_current():
    assert __version__ == "2.6.19"


# ---------------------------------------------------------------------------
# v2.6.2 — version consistency guard
# ---------------------------------------------------------------------------


class TestVersionConsistencyGuard:
    def _write_pyproject(self, tmp_path: Path, version: str) -> Path:
        p = tmp_path / "pyproject.toml"
        p.write_text(f'[project]\nname = "safecode-agent"\nversion = "{version}"\n', encoding="utf-8")
        return p

    def test_matching_versions_pass(self, tmp_path):
        pyproject = self._write_pyproject(tmp_path, "2.6.5")
        result = check_version_consistency(pyproject_path=pyproject, runtime_version="2.6.5")
        assert result.ok is True
        assert result.package_version == "2.6.5"
        assert result.runtime_version == "2.6.5"
        assert "OK" in result.message

    def test_mismatched_versions_fail_clearly(self, tmp_path):
        pyproject = self._write_pyproject(tmp_path, "2.5.0")
        result = check_version_consistency(pyproject_path=pyproject, runtime_version="2.6.5")
        assert result.ok is False
        assert result.package_version == "2.5.0"
        assert result.runtime_version == "2.6.5"
        assert "mismatch" in result.message.lower()
        assert "2.5.0" in result.message
        assert "2.6.5" in result.message

    def test_missing_pyproject_fails_clearly(self, tmp_path):
        missing = tmp_path / "nonexistent" / "pyproject.toml"
        result = check_version_consistency(pyproject_path=missing, runtime_version="2.6.5")
        assert result.ok is False
        assert "not found" in result.message.lower() or "pyproject" in result.message.lower()

    def test_malformed_pyproject_fails_clearly(self, tmp_path):
        bad = tmp_path / "pyproject.toml"
        bad.write_text("[project]\n# no version key\n", encoding="utf-8")
        result = check_version_consistency(pyproject_path=bad, runtime_version="2.6.5")
        assert result.ok is False
        assert "read error" in result.message.lower() or "version" in result.message.lower()

    def test_result_exposes_both_versions(self, tmp_path):
        pyproject = self._write_pyproject(tmp_path, "9.9.9")
        result = check_version_consistency(pyproject_path=pyproject, runtime_version="1.0.0")
        assert result.package_version == "9.9.9"
        assert result.runtime_version == "1.0.0"

    def test_real_repo_versions_are_consistent(self):
        """Guard against the v2.6.1 drift incident: repo pyproject.toml must match __version__."""
        result = check_version_consistency()
        assert result.ok is True, result.message


def test_doctor_reports_config_and_approval_env(tmp_path, monkeypatch):
    approval_dir = tmp_path.parent / "approvals"
    sandbox_dir = tmp_path.parent / "sandbox-approvals"
    monkeypatch.setenv("SAFECODE_APPROVAL_DIR", str(approval_dir))
    monkeypatch.setenv("SAFECODE_SANDBOX_APPROVAL_DIR", str(sandbox_dir))
    (tmp_path / ".sac").mkdir()
    (tmp_path / ".sac" / "config.toml").write_text("policy = \"normal\"\n", encoding="utf-8")

    checks = {check.name: check for check in Doctor(tmp_path).run()}

    assert checks["config"].passed is True
    assert checks["sac_dir"].passed is True
    assert checks["approval_dir"].detail == str(approval_dir)
    assert checks["sandbox_approval_dir"].detail == str(sandbox_dir)


def test_version_cli_runs():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "2.6.19" in result.output
    assert "git pull" in result.output


def test_doctor_cli_mentions_new_checks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "approval_dir" in result.output
    assert "sandbox_approval_dir" in result.output
