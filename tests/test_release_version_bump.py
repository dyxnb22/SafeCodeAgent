"""Tests for v2.6.10 release version bump helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from safecode.release.bump import BumpResult, bump_versions, render_bump_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PYPROJECT_TEMPLATE = """\
[project]
name = "safecode-agent"
version = "2.6.9"
description = "Test."
"""

_INIT_TEMPLATE = '''\
"""SafeCode Agent package."""

__version__ = "2.6.9"
'''

_TEST_TEMPLATE = '''\
import safecode

SENTINEL_VERSION = "2.6.9"

def test_doctor_cli_mentions_new_checks():
    assert "approval_dir" in result.output
'''


def _write_files(tmp_path: Path, version: str = "2.6.9") -> tuple[Path, Path, Path]:
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text(
        _PYPROJECT_TEMPLATE.replace("2.6.9", version), encoding="utf-8"
    )
    init = tmp_path / "__init__.py"
    init.write_text(_INIT_TEMPLATE.replace("2.6.9", version), encoding="utf-8")
    test = tmp_path / "test_polish.py"
    test.write_text(_TEST_TEMPLATE.replace("2.6.9", version), encoding="utf-8")
    return pyproj, init, test


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestBumpVersionsHappyPath:
    def test_updates_canonical_package_files(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        result = bump_versions(
            "2.6.10",
            pyproject_path=pyproj,
            init_path=init,
            test_path=test,
        )
        assert result.ok
        assert len(result.updated_files) == 2
        assert result.errors == []

    def test_pyproject_content_updated(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        bump_versions("2.6.10", pyproject_path=pyproj, init_path=init, test_path=test)
        assert 'version = "2.6.10"' in pyproj.read_text()

    def test_init_content_updated(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        bump_versions("2.6.10", pyproject_path=pyproj, init_path=init, test_path=test)
        assert '__version__ = "2.6.10"' in init.read_text()

    def test_test_file_content_not_updated(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        bump_versions("2.6.10", pyproject_path=pyproj, init_path=init, test_path=test)
        assert 'SENTINEL_VERSION = "2.6.9"' in test.read_text()

    def test_test_file_cli_output_expectation_not_updated(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        bump_versions("2.6.10", pyproject_path=pyproj, init_path=init, test_path=test)
        assert 'SENTINEL_VERSION = "2.6.9"' in test.read_text()

    def test_unrelated_result_output_expectation_preserved(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        bump_versions("2.6.10", pyproject_path=pyproj, init_path=init, test_path=test)
        assert 'assert "approval_dir" in result.output' in test.read_text()

    def test_new_version_in_result(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        result = bump_versions("2.7.0", pyproject_path=pyproj, init_path=init, test_path=test)
        assert result.new_version == "2.7.0"

    def test_old_version_not_present_after_bump(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        bump_versions("3.0.0", pyproject_path=pyproj, init_path=init, test_path=test)
        assert '2.6.9' not in pyproj.read_text()
        assert '2.6.9' not in init.read_text()


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

class TestBumpVersionsDryRun:
    def test_dry_run_does_not_write_files(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        bump_versions("9.9.9", pyproject_path=pyproj, init_path=init, test_path=test, dry_run=True)
        assert '2.6.9' in pyproj.read_text()
        assert '2.6.9' in init.read_text()

    def test_dry_run_reports_updated_files(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        result = bump_versions("9.9.9", pyproject_path=pyproj, init_path=init, test_path=test, dry_run=True)
        assert result.ok
        assert len(result.updated_files) == 2


# ---------------------------------------------------------------------------
# Invalid version
# ---------------------------------------------------------------------------

class TestBumpVersionsInvalidVersion:
    @pytest.mark.parametrize("bad", ["", "2.6", "v2.6.10", "2.6.10.0", "2.6.a"])
    def test_invalid_version_returns_error(self, bad: str, tmp_path: Path) -> None:
        result = bump_versions(bad)
        assert not result.ok
        assert result.errors
        assert bad in result.errors[0] or "Invalid" in result.errors[0]

    def test_invalid_version_does_not_write_files(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        bump_versions("bad-version", pyproject_path=pyproj, init_path=init, test_path=test)
        assert '2.6.9' in pyproj.read_text()


# ---------------------------------------------------------------------------
# Missing / optional files
# ---------------------------------------------------------------------------

class TestBumpVersionsMissingFiles:
    def test_missing_test_file_is_ignored(self, tmp_path: Path) -> None:
        pyproj, init, _ = _write_files(tmp_path)
        missing = tmp_path / "does_not_exist.py"
        result = bump_versions("2.6.10", pyproject_path=pyproj, init_path=init, test_path=missing)
        assert result.ok
        assert str(missing) not in result.skipped_files

    def test_missing_pyproject_skipped(self, tmp_path: Path) -> None:
        _, init, test = _write_files(tmp_path)
        missing = tmp_path / "no_pyproject.toml"
        result = bump_versions("2.6.10", pyproject_path=missing, init_path=init, test_path=test)
        assert result.ok
        assert str(missing) in result.skipped_files

    def test_project_root_default_test_path_is_not_touched(self, tmp_path: Path) -> None:
        pyproj, init, _ = _write_files(tmp_path)
        repo_test = tmp_path / "tests" / "test_install_update_polish.py"
        repo_test.parent.mkdir()
        repo_test.write_text(_TEST_TEMPLATE, encoding="utf-8")
        result = bump_versions(
            "2.6.10",
            project_root=tmp_path,
            pyproject_path=pyproj,
            init_path=init,
            test_path=None,
        )
        assert result.ok
        assert 'SENTINEL_VERSION = "2.6.9"' in repo_test.read_text()


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

class TestRenderBumpResult:
    def test_render_ok_result(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        result = bump_versions("2.6.10", pyproject_path=pyproj, init_path=init, test_path=test)
        text = render_bump_result(result)
        assert "2.6.10" in text
        assert "Version bumped successfully" in text

    def test_render_error_result(self) -> None:
        result = bump_versions("bad-version")
        text = render_bump_result(result)
        assert "Errors" in text or "Invalid" in text

    def test_render_includes_updated_file_paths(self, tmp_path: Path) -> None:
        pyproj, init, test = _write_files(tmp_path)
        result = bump_versions("2.6.10", pyproject_path=pyproj, init_path=init, test_path=test)
        text = render_bump_result(result)
        assert "pyproject.toml" in text or str(pyproj) in text


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

class TestReleaseBumpCLI:
    def test_cli_bump_updates_version(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner
        from safecode.cli import app

        pyproj, init, test = _write_files(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "release", "bump", "2.6.10",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_cli_bump_invalid_version_exits_1(self) -> None:
        from typer.testing import CliRunner
        from safecode.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["release", "bump", "bad-version"])
        assert result.exit_code == 1
