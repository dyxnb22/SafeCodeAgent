"""Tests for v2.6.18 doctor release diagnostics."""

from typer.testing import CliRunner

from safecode.cli import app
from safecode.doctor import Doctor


def test_doctor_includes_release_diagnostics(tmp_path) -> None:
    checks = {check.name: check for check in Doctor(tmp_path).run()}
    assert "release_version" in checks
    assert "release_tag" in checks
    assert "release_docs" in checks
    assert "release_preflight" in checks


def test_doctor_release_version_detail_is_actionable(tmp_path) -> None:
    check = {check.name: check for check in Doctor(tmp_path).run()}["release_version"]
    assert "pyproject" in check.detail.lower() or "version" in check.detail.lower()


def test_doctor_cli_lists_release_diagnostics(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "release_version" in result.output
    assert "release_tag" in result.output
    assert "release_docs" in result.output
    assert "release_preflight" in result.output
