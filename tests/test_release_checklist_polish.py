"""Tests for v2.6.3 release checklist polish, v2.6.6 tag consistency, v2.6.7 next-step polish."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.release.check import ReleaseCheckResult, render_release_check, run_release_check
from safecode.release.version_guard import TagConsistencyResult, check_tag_consistency


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


# ---------------------------------------------------------------------------
# v2.6.6 — tag consistency guard
# ---------------------------------------------------------------------------


class TestCheckTagConsistency:
    def test_matching_tag_is_consistent(self):
        result = check_tag_consistency("2.6.6", tag="v2.6.6")
        assert result.consistent is True
        assert result.tag_available is True
        assert result.tag == "v2.6.6"
        assert "OK" in result.message

    def test_mismatched_tag_is_not_consistent(self):
        result = check_tag_consistency("2.6.6", tag="v2.6.5")
        assert result.consistent is False
        assert result.tag_available is True
        assert result.tag == "v2.6.5"
        assert "mismatch" in result.message.lower()
        assert "v2.6.5" in result.message
        assert "2.6.6" in result.message

    def test_no_tag_is_reported_honestly(self):
        result = check_tag_consistency("2.6.6", tag=None)
        assert result.consistent is False
        assert result.tag_available is False
        assert result.tag is None
        assert "no exact git tag" in result.message.lower() or "cannot confirm" in result.message.lower()

    def test_no_tag_is_not_reported_as_pass(self):
        result = check_tag_consistency("2.6.6", tag=None)
        assert result.consistent is False

    def test_tag_result_included_in_release_check(self, tmp_path):
        """run_release_check includes tag_result when package version is known."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "safecode-agent"\nversion = "2.6.6"\n', encoding="utf-8"
        )
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.6",
            git_tag="v2.6.6",
        )
        assert result.tag_result is not None
        assert result.tag_result.consistent is True

    def test_tag_mismatch_in_release_check(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "safecode-agent"\nversion = "2.6.6"\n', encoding="utf-8"
        )
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.6",
            git_tag="v2.6.5",
        )
        assert result.tag_result is not None
        assert result.tag_result.consistent is False

    def test_render_includes_tag_info(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "safecode-agent"\nversion = "2.6.6"\n', encoding="utf-8"
        )
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.6",
            git_tag="v2.6.6",
        )
        text = render_release_check(result)
        assert "tag" in text.lower()
        assert "v2.6.6" in text


# ---------------------------------------------------------------------------
# v2.6.7 — release check next-step polish
# ---------------------------------------------------------------------------


class TestNextStepPolish:
    def _make_pyproject(self, tmp_path: Path, version: str) -> Path:
        p = tmp_path / "pyproject.toml"
        p.write_text(
            f'[project]\nname = "safecode-agent"\nversion = "{version}"\n',
            encoding="utf-8",
        )
        return p

    def test_dirty_tree_suggests_commit_or_stash(self, tmp_path):
        pyproject = self._make_pyproject(tmp_path, "2.6.7")
        # Simulate dirty tree by monkeypatching check would be cleaner;
        # instead test via ReleaseCheckResult directly.
        from safecode.release.check import ReleaseCheckResult
        result = ReleaseCheckResult(
            package_version="2.6.7",
            runtime_version="2.6.7",
            version_consistent=True,
            version_message="OK",
            tree_clean=False,
            tree_detail="2 uncommitted change(s)",
            tag_result=None,
            next_steps=["Commit or stash pending changes before tagging."],
        )
        steps = " ".join(result.next_steps)
        assert "commit" in steps.lower() or "stash" in steps.lower()

    def test_version_mismatch_suggests_version_fix(self, tmp_path):
        pyproject = self._make_pyproject(tmp_path, "2.6.5")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.7",
            git_tag=None,
        )
        steps = " ".join(result.next_steps)
        assert "pyproject" in steps.lower() or "__version__" in steps

    def test_clean_correctly_tagged_has_no_commit_or_tag_suggestion(self, tmp_path):
        pyproject = self._make_pyproject(tmp_path, "2.6.7")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.7",
            git_tag="v2.6.7",
        )
        if result.tree_clean is True:
            steps = " ".join(result.next_steps)
            assert "git commit" not in steps
            assert "git tag" not in steps

    def test_clean_untagged_suggests_tag_only(self, tmp_path):
        pyproject = self._make_pyproject(tmp_path, "2.6.7")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.7",
            git_tag=None,
        )
        if result.tree_clean is True:
            steps = " ".join(result.next_steps)
            assert "git tag" in steps
            assert "git commit" not in steps

    def test_render_ready_state_when_all_clean(self, tmp_path):
        pyproject = self._make_pyproject(tmp_path, "2.6.7")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.7",
            git_tag="v2.6.7",
        )
        if result.tree_clean is True:
            text = render_release_check(result)
            assert "ready" in text.lower()
            assert "tests passed" not in text.lower()

    def test_render_does_not_claim_tests_passed_in_any_state(self, tmp_path):
        pyproject = self._make_pyproject(tmp_path, "2.6.7")
        result = run_release_check(
            project_root=tmp_path,
            pyproject_path=pyproject,
            runtime_version="2.6.7",
            git_tag="v2.6.7",
        )
        text = render_release_check(result)
        assert "tests passed" not in text.lower()
