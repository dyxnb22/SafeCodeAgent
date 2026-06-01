"""Tests for v2.6.3 release checklist command polish."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.release.check import ReleaseCheckResult, render_release_check, run_release_check


# ---------------------------------------------------------------------------
# run_release_check helper
# ---------------------------------------------------------------------------


class TestRunReleaseCheck:
    def _write_pyproject(self, tmp_path: Path, version: str) -> Path:
        p = tmp_path / "pyproject.toml"
        p.write_text(
            f'[project]\nname = "safecode-agent"\nversion = "{version}"\n',
            encoding="utf-8",
        )
        return p

    def test_matching_version_is_consistent(self, tmp_path):
        pyproject = self._write_pyproject(tmp_path, "2.6.1")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.1",
        )
        assert result.version_consistent is True
        assert result.package_version == "2.6.1"
        assert result.runtime_version == "2.6.1"

    def test_mismatched_version_is_not_consistent(self, tmp_path):
        pyproject = self._write_pyproject(tmp_path, "2.5.0")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.1",
        )
        assert result.version_consistent is False
        assert result.package_version == "2.5.0"
        assert result.runtime_version == "2.6.1"

    def test_next_steps_present_on_mismatch(self, tmp_path):
        pyproject = self._write_pyproject(tmp_path, "2.5.0")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.1",
        )
        assert any("pyproject" in s.lower() or "__version__" in s for s in result.next_steps)

    def test_tree_detail_is_populated(self, tmp_path):
        pyproject = self._write_pyproject(tmp_path, "2.6.1")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.1",
        )
        # tree_clean may be True/False/None depending on git availability in test env
        assert isinstance(result.tree_detail, str)
        assert len(result.tree_detail) > 0

    def test_ok_requires_consistent_version(self, tmp_path):
        pyproject = self._write_pyproject(tmp_path, "2.5.0")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.1",
        )
        assert result.ok is False

    def test_consistent_clean_tree_suggests_tag_commands(self, tmp_path):
        pyproject = self._write_pyproject(tmp_path, "1.2.3")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="1.2.3",
        )
        if result.tree_clean is True:
            steps_text = " ".join(result.next_steps)
            assert "git tag" in steps_text or "pytest" in steps_text


# ---------------------------------------------------------------------------
# render_release_check
# ---------------------------------------------------------------------------


class TestRenderReleaseCheck:
    def _make_result(
        self,
        *,
        package_version: str = "2.6.1",
        runtime_version: str = "2.6.1",
        version_consistent: bool = True,
        version_message: str = "OK — both versions are 2.6.1",
        tree_clean: bool | None = True,
        tree_detail: str = "working tree clean",
        next_steps: list[str] | None = None,
    ) -> ReleaseCheckResult:
        return ReleaseCheckResult(
            package_version=package_version,
            runtime_version=runtime_version,
            version_consistent=version_consistent,
            version_message=version_message,
            tree_clean=tree_clean,
            tree_detail=tree_detail,
            next_steps=next_steps or [],
        )

    def test_render_includes_package_version(self):
        result = self._make_result()
        text = render_release_check(result)
        assert "2.6.1" in text

    def test_render_includes_runtime_version(self):
        result = self._make_result()
        text = render_release_check(result)
        assert "2.6.1" in text

    def test_render_shows_yes_for_consistent(self):
        result = self._make_result(version_consistent=True)
        text = render_release_check(result)
        assert "yes" in text.lower()

    def test_render_shows_no_for_inconsistent(self):
        result = self._make_result(version_consistent=False, version_message="mismatch")
        text = render_release_check(result)
        assert "no" in text.lower() or "NO" in text

    def test_render_includes_tree_detail(self):
        result = self._make_result(tree_detail="3 uncommitted change(s)")
        text = render_release_check(result)
        assert "3 uncommitted" in text

    def test_render_includes_next_steps_when_present(self):
        result = self._make_result(next_steps=["Do the thing"])
        text = render_release_check(result)
        assert "Do the thing" in text

    def test_render_does_not_claim_tests_passed(self):
        result = self._make_result()
        text = render_release_check(result)
        assert "tests passed" not in text.lower()


# ---------------------------------------------------------------------------
# CLI: sac release check
# ---------------------------------------------------------------------------


class TestReleaseCheckCLI:
    def _write_pyproject(self, tmp_path: Path, version: str) -> None:
        (tmp_path / "pyproject.toml").write_text(
            f'[project]\nname = "safecode-agent"\nversion = "{version}"\n',
            encoding="utf-8",
        )

    def test_cli_check_exits_zero_on_consistent_version(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self._write_pyproject(tmp_path, "2.6.1")
        # We patch run_release_check to avoid git subprocess in tests
        from safecode import cli_ops
        original = cli_ops.run_release_check

        def _fake_run(project_root=None, **kwargs):
            from safecode.release.check import ReleaseCheckResult
            return ReleaseCheckResult(
                package_version="2.6.1",
                runtime_version="2.6.1",
                version_consistent=True,
                version_message="OK — both versions are 2.6.1",
                tree_clean=True,
                tree_detail="working tree clean",
                next_steps=[],
            )

        monkeypatch.setattr(cli_ops, "run_release_check", _fake_run)
        result = CliRunner().invoke(app, ["release", "check"])
        assert result.exit_code == 0
        assert "2.6.1" in result.output

    def test_cli_check_exits_nonzero_on_mismatch(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from safecode import cli_ops

        def _fake_run(project_root=None, **kwargs):
            from safecode.release.check import ReleaseCheckResult
            return ReleaseCheckResult(
                package_version="2.5.0",
                runtime_version="2.6.1",
                version_consistent=False,
                version_message="Version mismatch: pyproject says 2.5.0 but __version__ is 2.6.1",
                tree_clean=True,
                tree_detail="working tree clean",
                next_steps=["Update one to match."],
            )

        monkeypatch.setattr(cli_ops, "run_release_check", _fake_run)
        result = CliRunner().invoke(app, ["release", "check"])
        assert result.exit_code != 0
        assert "2.5.0" in result.output or "mismatch" in result.output.lower()

    def test_cli_check_output_includes_version_fields(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from safecode import cli_ops

        def _fake_run(project_root=None, **kwargs):
            from safecode.release.check import ReleaseCheckResult
            return ReleaseCheckResult(
                package_version="2.6.1",
                runtime_version="2.6.1",
                version_consistent=True,
                version_message="OK — both versions are 2.6.1",
                tree_clean=True,
                tree_detail="working tree clean",
                next_steps=[],
            )

        monkeypatch.setattr(cli_ops, "run_release_check", _fake_run)
        result = CliRunner().invoke(app, ["release", "check"])
        assert "pyproject" in result.output.lower() or "2.6.1" in result.output
        assert "__version__" in result.output or "2.6.1" in result.output
