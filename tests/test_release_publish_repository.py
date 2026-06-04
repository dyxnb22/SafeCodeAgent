"""Tests for v3.9.0 T-3.9.0-B: sac release publish --repository.

Constraints enforced:
- No live network calls in any test.
- Real publish (test-pypi or pypi) still requires SAFECODE_PUBLISH=1.
- Dry-run with --repository test-pypi is deterministic and safe.
- Unknown repository fails closed.
- Production publish gate is not weakened by adding test-pypi lane.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.release.publish import (
    PublishResult,
    _REPOSITORY_URLS,
    _planned_steps,
    render_publish_result,
    run_release_publish,
)

runner = CliRunner()


# ── Repository URL registry ───────────────────────────────────────────────────


class TestRepositoryURLRegistry:
    def test_pypi_url_registered(self):
        assert "pypi" in _REPOSITORY_URLS
        assert "upload.pypi.org" in _REPOSITORY_URLS["pypi"]

    def test_test_pypi_url_registered(self):
        assert "test-pypi" in _REPOSITORY_URLS
        assert "test.pypi.org" in _REPOSITORY_URLS["test-pypi"]

    def test_test_pypi_url_differs_from_pypi(self):
        assert _REPOSITORY_URLS["test-pypi"] != _REPOSITORY_URLS["pypi"]


# ── Dry-run with repository ───────────────────────────────────────────────────


class TestDryRunWithRepository:
    def test_dry_run_test_pypi_ok(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True, repository="test-pypi")
        assert result.ok is True
        assert result.dry_run is True
        assert result.repository == "test-pypi"

    def test_dry_run_test_pypi_steps_have_prefix(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True, repository="test-pypi")
        for step in result.steps:
            assert step.startswith("[dry-run]")

    def test_dry_run_test_pypi_upload_step_mentions_test_pypi(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True, repository="test-pypi")
        upload_steps = [s for s in result.steps if "upload" in s]
        assert upload_steps
        assert "test-pypi" in upload_steps[0].lower()

    def test_dry_run_pypi_default_no_test_label(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True, repository="pypi")
        upload_steps = [s for s in result.steps if "upload" in s]
        assert upload_steps
        assert "test-pypi" not in upload_steps[0].lower()

    def test_dry_run_no_subprocess(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            run_release_publish(tmp_path, dry_run=True, repository="test-pypi")
            mock_run.assert_not_called()

    def test_dry_run_deterministic(self, tmp_path):
        r1 = run_release_publish(tmp_path, dry_run=True, repository="test-pypi")
        r2 = run_release_publish(tmp_path, dry_run=True, repository="test-pypi")
        assert r1.steps == r2.steps
        assert r1.ok == r2.ok


# ── Unknown repository fails closed ──────────────────────────────────────────


class TestUnknownRepository:
    def test_unknown_repository_returns_failure(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True, repository="bad-repo")
        assert result.ok is False

    def test_unknown_repository_error_message(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True, repository="bad-repo")
        assert any("bad-repo" in e for e in result.errors)

    def test_unknown_repository_lists_known_values(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True, repository="xyz")
        combined = " ".join(result.errors)
        assert "pypi" in combined or "test-pypi" in combined

    def test_unknown_repository_no_subprocess(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            run_release_publish(tmp_path, dry_run=False, repository="nowhere")
            mock_run.assert_not_called()


# ── Real publish gating for test-pypi ────────────────────────────────────────


class TestRealPublishTestPyPIGating:
    def test_test_pypi_real_blocked_without_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAFECODE_PUBLISH", raising=False)
        result = run_release_publish(tmp_path, dry_run=False, repository="test-pypi")
        assert result.ok is False
        assert any("SAFECODE_PUBLISH" in e for e in result.errors)

    def test_test_pypi_real_blocked_no_subprocess_without_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAFECODE_PUBLISH", raising=False)
        with patch("subprocess.run") as mock_run:
            run_release_publish(tmp_path, dry_run=False, repository="test-pypi")
            mock_run.assert_not_called()

    def test_test_pypi_real_uses_test_pypi_url(self, tmp_path, monkeypatch):
        """When real upload runs, it must use the test.pypi.org URL."""
        monkeypatch.setenv("SAFECODE_PUBLISH", "1")
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            m = MagicMock()
            m.returncode = 0
            return m

        with patch("safecode.release.publish.check_version_consistency") as mock_vc, \
             patch("safecode.release.publish.check_tag_consistency") as mock_tc, \
             patch("safecode.release.publish.shutil.rmtree"), \
             patch("safecode.release.publish.Path.glob", return_value=[]), \
             patch("subprocess.run", side_effect=fake_run):
            mock_vc.return_value = MagicMock(ok=True, package_version="3.9.0")
            mock_tc.return_value = MagicMock(consistent=True)
            run_release_publish(tmp_path, dry_run=False, repository="test-pypi")

        upload_calls = [c for c in calls if "publish" in c]
        assert upload_calls, "expected an upload call"
        upload_args = " ".join(upload_calls[0])
        assert "test.pypi.org" in upload_args

    def test_pypi_real_uses_pypi_url(self, tmp_path, monkeypatch):
        """Production publish uses the production PyPI URL."""
        monkeypatch.setenv("SAFECODE_PUBLISH", "1")
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            m = MagicMock()
            m.returncode = 0
            return m

        with patch("safecode.release.publish.check_version_consistency") as mock_vc, \
             patch("safecode.release.publish.check_tag_consistency") as mock_tc, \
             patch("safecode.release.publish.shutil.rmtree"), \
             patch("safecode.release.publish.Path.glob", return_value=[]), \
             patch("subprocess.run", side_effect=fake_run):
            mock_vc.return_value = MagicMock(ok=True, package_version="3.9.0")
            mock_tc.return_value = MagicMock(consistent=True)
            run_release_publish(tmp_path, dry_run=False, repository="pypi")

        upload_calls = [c for c in calls if "publish" in c]
        assert upload_calls
        upload_args = " ".join(upload_calls[0])
        assert "upload.pypi.org" in upload_args


# ── Planned steps with repository ────────────────────────────────────────────


class TestPlannedStepsRepository:
    def test_steps_test_pypi_label_in_upload(self):
        steps = _planned_steps(sign=False, repository="test-pypi")
        upload = [s for s in steps if "upload" in s][0]
        assert "test-pypi" in upload.lower()

    def test_steps_pypi_no_test_label(self):
        steps = _planned_steps(sign=False, repository="pypi")
        upload = [s for s in steps if "upload" in s][0]
        assert "test-pypi" not in upload.lower()


# ── PublishResult repository field ───────────────────────────────────────────


class TestPublishResultRepository:
    def test_repository_field_present(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True, repository="test-pypi")
        assert result.repository == "test-pypi"

    def test_repository_default_is_pypi(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True)
        assert result.repository == "pypi"

    def test_render_shows_test_pypi(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True, repository="test-pypi")
        text = render_publish_result(result)
        assert "test-pypi" in text


# ── CLI: --repository option ──────────────────────────────────────────────────


class TestCLIRepositoryOption:
    def test_repository_option_in_help(self):
        result = runner.invoke(app, ["release", "publish", "--help"])
        assert result.exit_code == 0
        assert "repository" in result.output.lower()

    def test_dry_run_test_pypi_via_cli(self):
        result = runner.invoke(app, ["release", "publish", "--repository", "test-pypi"])
        assert result.exit_code == 0
        assert "test-pypi" in result.output.lower()

    def test_dry_run_pypi_via_cli(self):
        result = runner.invoke(app, ["release", "publish", "--repository", "pypi"])
        assert result.exit_code == 0

    def test_unknown_repository_via_cli(self):
        result = runner.invoke(app, ["release", "publish", "--repository", "nowhere"])
        assert result.exit_code != 0

    def test_json_includes_repository(self):
        result = runner.invoke(
            app, ["release", "publish", "--json", "--repository", "test-pypi"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["repository"] == "test-pypi"

    def test_no_dry_run_test_pypi_blocked_without_env(self, monkeypatch):
        monkeypatch.delenv("SAFECODE_PUBLISH", raising=False)
        result = runner.invoke(
            app, ["release", "publish", "--no-dry-run", "--repository", "test-pypi"]
        )
        assert result.exit_code != 0
        assert "SAFECODE_PUBLISH" in result.output
