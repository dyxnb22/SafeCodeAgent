"""Tests for v3.6.0 release publish (T-3.6.0-A).

Constraints enforced:
- Dry-run is deterministic: no subprocess, no file writes, no network.
- Real publish is never executed in tests.
- Real publish requires SAFECODE_PUBLISH=1 + clean tag.
- Sign fails closed when no signing tool is found.
- No existing release preflight, versions governance, or docs guard weakened.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.release.publish import (
    PublishResult,
    _check_sign_tooling,
    _planned_steps,
    render_publish_result,
    run_release_publish,
)

runner = CliRunner()


# ── Planned steps ─────────────────────────────────────────────────────────────


class TestPlannedSteps:
    def test_steps_without_sign(self):
        steps = _planned_steps(sign=False)
        assert any("build" in s for s in steps)
        assert any("upload" in s for s in steps)
        assert not any("sign" in s for s in steps)

    def test_steps_with_sign(self):
        steps = _planned_steps(sign=True)
        assert any("build" in s for s in steps)
        assert any("sign" in s for s in steps)
        assert any("upload" in s for s in steps)

    def test_steps_order(self):
        steps = _planned_steps(sign=True)
        labels = [s.split(":")[0] for s in steps]
        assert labels.index("build") < labels.index("sign")
        assert labels.index("sign") < labels.index("upload")

    def test_steps_order_no_sign(self):
        steps = _planned_steps(sign=False)
        labels = [s.split(":")[0] for s in steps]
        assert labels.index("build") < labels.index("upload")


# ── Dry-run determinism ───────────────────────────────────────────────────────


class TestDryRunDeterminism:
    def test_dry_run_ok(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True)
        assert result.ok is True
        assert result.dry_run is True
        assert result.errors == ()

    def test_dry_run_steps_prefixed(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True)
        for step in result.steps:
            assert step.startswith("[dry-run]"), f"step missing prefix: {step!r}"

    def test_dry_run_no_subprocess(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            run_release_publish(tmp_path, dry_run=True)
            mock_run.assert_not_called()

    def test_dry_run_no_file_writes(self, tmp_path):
        initial_files = set(tmp_path.rglob("*"))
        run_release_publish(tmp_path, dry_run=True)
        final_files = set(tmp_path.rglob("*"))
        assert initial_files == final_files

    def test_dry_run_deterministic(self, tmp_path):
        r1 = run_release_publish(tmp_path, dry_run=True)
        r2 = run_release_publish(tmp_path, dry_run=True)
        assert r1.steps == r2.steps
        assert r1.ok == r2.ok

    def test_dry_run_with_sign_shows_sign_step(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True, sign=True)
        assert result.ok is True
        assert any("sign" in s for s in result.steps)

    def test_dry_run_with_sign_no_subprocess(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            with patch("shutil.which", return_value=None):
                run_release_publish(tmp_path, dry_run=True, sign=True)
                mock_run.assert_not_called()


# ── Real publish gating ───────────────────────────────────────────────────────


class TestRealPublishGating:
    def test_real_publish_blocked_without_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAFECODE_PUBLISH", raising=False)
        result = run_release_publish(tmp_path, dry_run=False)
        assert result.ok is False
        assert result.dry_run is False
        assert any("SAFECODE_PUBLISH" in e for e in result.errors)

    def test_real_publish_blocked_no_subprocess_without_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAFECODE_PUBLISH", raising=False)
        with patch("subprocess.run") as mock_run:
            run_release_publish(tmp_path, dry_run=False)
            mock_run.assert_not_called()

    def test_real_publish_blocked_on_version_inconsistency(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_PUBLISH", "1")
        with patch(
            "safecode.release.publish.check_version_consistency"
        ) as mock_vc:
            mock_vc.return_value = MagicMock(ok=False, message="version mismatch")
            result = run_release_publish(tmp_path, dry_run=False)
        assert result.ok is False
        assert any("version inconsistency" in e for e in result.errors)

    def test_real_publish_blocked_on_dirty_tag(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_PUBLISH", "1")
        with patch("safecode.release.publish.check_version_consistency") as mock_vc:
            mock_vc.return_value = MagicMock(ok=True, package_version="3.6.1")
            with patch("safecode.release.publish.check_tag_consistency") as mock_tc:
                mock_tc.return_value = MagicMock(
                    consistent=False, message="no exact tag at HEAD"
                )
                result = run_release_publish(tmp_path, dry_run=False)
        assert result.ok is False
        assert any("tag check failed" in e for e in result.errors)

    def test_real_publish_never_runs_build_without_clean_tag(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_PUBLISH", "1")
        with patch("safecode.release.publish.check_version_consistency") as mock_vc:
            mock_vc.return_value = MagicMock(ok=True, package_version="3.6.1")
            with patch("safecode.release.publish.check_tag_consistency") as mock_tc:
                mock_tc.return_value = MagicMock(
                    consistent=False, message="no exact tag"
                )
                with patch("subprocess.run") as mock_run:
                    run_release_publish(tmp_path, dry_run=False)
                    mock_run.assert_not_called()


# ── Sign fails closed ─────────────────────────────────────────────────────────


class TestSignFailsClosed:
    def test_sign_tool_check_no_tools(self):
        with patch("shutil.which", return_value=None):
            error = _check_sign_tooling()
        assert error is not None
        assert "cosign" in error or "gpg" in error

    def test_sign_tool_check_cosign_available(self):
        with patch("shutil.which", side_effect=lambda t: "/usr/bin/cosign" if t == "cosign" else None):
            error = _check_sign_tooling()
        assert error is None

    def test_sign_tool_check_gpg_available(self):
        with patch("shutil.which", side_effect=lambda t: "/usr/bin/gpg" if t == "gpg" else None):
            error = _check_sign_tooling()
        assert error is None

    def test_sign_fails_closed_in_real_publish(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_PUBLISH", "1")
        with patch("safecode.release.publish.check_version_consistency") as mock_vc:
            mock_vc.return_value = MagicMock(ok=True, package_version="3.6.1")
            with patch("safecode.release.publish.check_tag_consistency") as mock_tc:
                mock_tc.return_value = MagicMock(consistent=True)
                with patch("shutil.which", return_value=None):
                    result = run_release_publish(tmp_path, dry_run=False, sign=True)
        assert result.ok is False
        assert any("signing" in e or "sign" in e for e in result.errors)

    def test_sign_dry_run_does_not_check_tooling(self, tmp_path):
        with patch("shutil.which", return_value=None):
            result = run_release_publish(tmp_path, dry_run=True, sign=True)
        assert result.ok is True


# ── PublishResult dataclass ───────────────────────────────────────────────────


class TestPublishResultShape:
    def test_result_is_frozen(self):
        r = PublishResult(dry_run=True, ok=True, steps=("s1",), errors=())
        with pytest.raises((AttributeError, TypeError)):
            r.ok = False  # type: ignore[misc]

    def test_result_steps_is_tuple(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True)
        assert isinstance(result.steps, tuple)

    def test_result_errors_is_tuple(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True)
        assert isinstance(result.errors, tuple)

    def test_result_errors_empty_on_dry_run(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True)
        assert result.errors == ()


# ── Render ────────────────────────────────────────────────────────────────────


class TestRenderPublishResult:
    def test_render_dry_run_pass(self):
        r = PublishResult(dry_run=True, ok=True, steps=("[dry-run] build: uv build",), errors=())
        text = render_publish_result(r)
        assert "PASS" in text
        assert "dry-run" in text
        assert "build" in text

    def test_render_fail_shows_errors(self):
        r = PublishResult(dry_run=False, ok=False, steps=(), errors=("tag check failed",))
        text = render_publish_result(r)
        assert "FAIL" in text
        assert "tag check failed" in text

    def test_render_no_test_secrets_in_output(self):
        r = PublishResult(dry_run=True, ok=True, steps=("[dry-run] build",), errors=())
        text = render_publish_result(r)
        assert "SAFECODE_PUBLISH" not in text

    def test_render_is_deterministic(self):
        r = PublishResult(dry_run=True, ok=True, steps=("[dry-run] build",), errors=())
        assert render_publish_result(r) == render_publish_result(r)


# ── CLI surface ───────────────────────────────────────────────────────────────


class TestCLIPublish:
    def test_publish_help_visible(self):
        result = runner.invoke(app, ["release", "publish", "--help"])
        assert result.exit_code == 0
        assert "publish" in result.output.lower() or "dry-run" in result.output.lower()

    def test_publish_dry_run_default_safe(self):
        result = runner.invoke(app, ["release", "publish"])
        # Dry-run default: always safe, exit 0
        assert result.exit_code == 0
        assert "dry-run" in result.output.lower() or "[dry-run]" in result.output

    def test_publish_no_dry_run_blocked_without_env(self, monkeypatch):
        monkeypatch.delenv("SAFECODE_PUBLISH", raising=False)
        result = runner.invoke(app, ["release", "publish", "--no-dry-run"])
        assert result.exit_code != 0
        assert "SAFECODE_PUBLISH" in result.output

    def test_publish_json_dry_run(self):
        result = runner.invoke(app, ["release", "publish", "--json"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["data"]["dry_run"] is True

    def test_publish_shows_in_release_help(self):
        result = runner.invoke(app, ["release", "--help"])
        assert result.exit_code == 0
        assert "publish" in result.output


# ── v3.9.0 T-3.9.0-A: signing truthing ───────────────────────────────────────


class TestSigningMechanismDescription:
    """Dry-run output must describe the actual signing mechanism (detached sig)."""

    def test_sign_step_mentions_detached(self, tmp_path):
        steps = _planned_steps(sign=True)
        sign_steps = [s for s in steps if "sign" in s]
        assert sign_steps, "expected a sign step"
        combined = " ".join(sign_steps).lower()
        assert "detach" in combined or "detached" in combined

    def test_sign_step_mentions_cosign_or_gpg(self, tmp_path):
        steps = _planned_steps(sign=True)
        sign_steps = [s for s in steps if "sign" in s]
        combined = " ".join(sign_steps).lower()
        assert "cosign" in combined or "gpg" in combined

    def test_sign_step_does_not_claim_sigstore_rekor(self, tmp_path):
        steps = _planned_steps(sign=True)
        combined = " ".join(steps).lower()
        assert "rekor" not in combined, "step should not claim Sigstore Rekor"

    def test_dry_run_sign_step_prefixed(self, tmp_path):
        result = run_release_publish(tmp_path, dry_run=True, sign=True)
        sign_steps = [s for s in result.steps if "sign" in s]
        for s in sign_steps:
            assert s.startswith("[dry-run]")

    def test_sign_error_mentions_detached_not_sigstore(self):
        with patch("shutil.which", return_value=None):
            error = _check_sign_tooling()
        assert error is not None
        assert "detach" in error.lower() or "detached" in error.lower()

    def test_render_includes_repository_label(self):
        from safecode.release.publish import PublishResult, render_publish_result
        r = PublishResult(dry_run=True, ok=True, steps=("[dry-run] build",), errors=(), repository="pypi")
        text = render_publish_result(r)
        assert "repository=pypi" in text
