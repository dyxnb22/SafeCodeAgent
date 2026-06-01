"""Tests for doctor environment checks plus opt-in release diagnostics."""

from typer.testing import CliRunner

from safecode.cli import app
from safecode.doctor import Doctor


def test_doctor_default_skips_release_diagnostics(tmp_path) -> None:
    checks = {check.name: check for check in Doctor(tmp_path).run()}
    assert "release_version" not in checks
    assert "release_tag" not in checks
    assert "release_docs" not in checks
    assert "release_preflight" not in checks


def test_doctor_release_mode_includes_release_diagnostics(tmp_path) -> None:
    checks = {check.name: check for check in Doctor(tmp_path).run(release=True)}
    assert "release_version" in checks
    assert "release_tag" in checks
    assert "release_docs" in checks
    assert "release_preflight" in checks


def test_doctor_release_version_detail_is_actionable(tmp_path) -> None:
    check = {check.name: check for check in Doctor(tmp_path).run(release=True)}["release_version"]
    assert "pyproject" in check.detail.lower() or "version" in check.detail.lower()


def test_doctor_cli_skips_release_diagnostics_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "release_version" not in result.output
    assert "release_tag" not in result.output
    assert "release_docs" not in result.output
    assert "release_preflight" not in result.output


def test_doctor_cli_lists_release_diagnostics_when_requested(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["doctor", "--release"])
    assert result.exit_code == 0
    assert "release_version" in result.output
    assert "release_tag" in result.output
    assert "release_docs" in result.output
    assert "release_preflight" in result.output
