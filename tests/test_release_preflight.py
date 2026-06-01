"""Tests for v2.6.11 release preflight aggregation."""

from typer.testing import CliRunner

from safecode.cli import app
from safecode.release.check import ReleaseCheckResult
from safecode.release.docs_guard import DocsGuardResult
from safecode.release.metadata import ReleaseMetadata
from safecode.release.preflight import (
    render_release_preflight,
    run_release_preflight,
)
from safecode.release.smoke import SmokeTestCase, SmokeTestResult
from safecode.release.version_guard import TagConsistencyResult


def _release_check(ok: bool = True) -> ReleaseCheckResult:
    return ReleaseCheckResult(
        package_version="2.6.11",
        runtime_version="2.6.11",
        version_consistent=ok,
        version_message="OK" if ok else "Version mismatch",
        tree_clean=True if ok else False,
        tree_detail="working tree clean" if ok else "1 uncommitted change(s)",
        tag_result=TagConsistencyResult(
            tag="v2.6.11" if ok else "v2.6.10",
            tag_available=True,
            consistent=ok,
            package_version="2.6.11",
            message="OK" if ok else "Tag mismatch",
        ),
        next_steps=[] if ok else ["Commit or stash pending changes before tagging."],
    )


def _smoke(ok: bool = True) -> SmokeTestResult:
    return SmokeTestResult(
        cases=[
            SmokeTestCase(
                name="import_version",
                passed=ok,
                detail="ok" if ok else "import failed",
            )
        ]
    )


def _metadata(ok: bool = True) -> ReleaseMetadata:
    return ReleaseMetadata(
        package_version="2.6.11",
        runtime_version="2.6.11",
        latest_git_tag="v2.6.11",
        version_note_files=["v2.6.11-release-preflight.md"],
        has_version_note=ok,
        skill_mentions_version=ok,
        issues=[] if ok else ["No version-note file found for v2.6.11."],
    )


def _docs(ok: bool = True) -> DocsGuardResult:
    return DocsGuardResult(
        has_version_note=ok,
        skill_mentions_version=ok,
        release_commands_documented=ok,
        issues=[] if ok else ["SKILL.md does not mention version 2.6.11."],
    )


class TestRunReleasePreflight:
    def test_all_subchecks_pass(self, tmp_path):
        result = run_release_preflight(
            tmp_path,
            release_check_runner=lambda root: _release_check(True),
            smoke_runner=lambda: _smoke(True),
            metadata_runner=lambda root: _metadata(True),
            docs_runner=lambda version, root: _docs(True),
        )
        assert result.ok is True

    def test_release_check_failure_fails_preflight(self, tmp_path):
        result = run_release_preflight(
            tmp_path,
            release_check_runner=lambda root: _release_check(False),
            smoke_runner=lambda: _smoke(True),
            metadata_runner=lambda root: _metadata(True),
            docs_runner=lambda version, root: _docs(True),
        )
        assert result.ok is False

    def test_smoke_failure_fails_preflight(self, tmp_path):
        result = run_release_preflight(
            tmp_path,
            release_check_runner=lambda root: _release_check(True),
            smoke_runner=lambda: _smoke(False),
            metadata_runner=lambda root: _metadata(True),
            docs_runner=lambda version, root: _docs(True),
        )
        assert result.ok is False

    def test_metadata_failure_fails_preflight(self, tmp_path):
        result = run_release_preflight(
            tmp_path,
            release_check_runner=lambda root: _release_check(True),
            smoke_runner=lambda: _smoke(True),
            metadata_runner=lambda root: _metadata(False),
            docs_runner=lambda version, root: _docs(True),
        )
        assert result.ok is False

    def test_docs_failure_fails_preflight(self, tmp_path):
        result = run_release_preflight(
            tmp_path,
            release_check_runner=lambda root: _release_check(True),
            smoke_runner=lambda: _smoke(True),
            metadata_runner=lambda root: _metadata(True),
            docs_runner=lambda version, root: _docs(False),
        )
        assert result.ok is False

    def test_docs_runner_receives_metadata_version(self, tmp_path):
        seen: list[str] = []

        def _docs_runner(version, root):
            seen.append(version)
            return _docs(True)

        run_release_preflight(
            tmp_path,
            release_check_runner=lambda root: _release_check(True),
            smoke_runner=lambda: _smoke(True),
            metadata_runner=lambda root: _metadata(True),
            docs_runner=_docs_runner,
        )
        assert seen == ["2.6.11"]


class TestRenderReleasePreflight:
    def test_render_pass(self, tmp_path):
        result = run_release_preflight(
            tmp_path,
            release_check_runner=lambda root: _release_check(True),
            smoke_runner=lambda: _smoke(True),
            metadata_runner=lambda root: _metadata(True),
            docs_runner=lambda version, root: _docs(True),
        )
        text = render_release_preflight(result)
        assert "Release preflight passed" in text
        assert "[PASS] release check" in text

    def test_render_failure_is_concise(self, tmp_path):
        result = run_release_preflight(
            tmp_path,
            release_check_runner=lambda root: _release_check(False),
            smoke_runner=lambda: _smoke(False),
            metadata_runner=lambda root: _metadata(False),
            docs_runner=lambda version, root: _docs(False),
        )
        text = render_release_preflight(result)
        assert "Failures:" in text
        assert "release check" in text
        assert "smoke" in text
        assert "metadata" in text
        assert "docs" in text


class TestReleasePreflightCLI:
    def test_cli_success(self, monkeypatch):
        from safecode import cli_ops

        monkeypatch.setattr(
            cli_ops,
            "run_release_preflight",
            lambda root: run_release_preflight(
                root,
                release_check_runner=lambda _root: _release_check(True),
                smoke_runner=lambda: _smoke(True),
                metadata_runner=lambda _root: _metadata(True),
                docs_runner=lambda version, _root: _docs(True),
            ),
        )
        result = CliRunner().invoke(app, ["release", "preflight"])
        assert result.exit_code == 0
        assert "Release preflight passed" in result.output

    def test_cli_failure_exits_1(self, monkeypatch):
        from safecode import cli_ops

        monkeypatch.setattr(
            cli_ops,
            "run_release_preflight",
            lambda root: run_release_preflight(
                root,
                release_check_runner=lambda _root: _release_check(False),
                smoke_runner=lambda: _smoke(True),
                metadata_runner=lambda _root: _metadata(True),
                docs_runner=lambda version, _root: _docs(True),
            ),
        )
        result = CliRunner().invoke(app, ["release", "preflight"])
        assert result.exit_code == 1
