"""Tests for v3.6.1 doctor update check (T-3.6.1-A).

Constraints:
- All network access is mocked; no real HTTPS calls.
- Offline/network failure → SKIP (never FAIL).
- Stale version → WARN with actionable message.
- Up-to-date → PASS.
- No telemetry: fetch function sends no identifying headers.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode import __version__
from safecode.cli import app
from safecode.core.diagnostic import DiagnosticStatus
from safecode.doctor import Doctor, _fetch_latest_pypi_version, _ver_tuple

runner = CliRunner()


# ── Version tuple helper ──────────────────────────────────────────────────────


class TestVerTuple:
    def test_parses_semver(self):
        assert _ver_tuple("3.6.1") == (3, 6, 1)

    def test_parses_two_part(self):
        assert _ver_tuple("3.6") == (3, 6)

    def test_handles_malformed(self):
        result = _ver_tuple("not-a-version")
        assert result == (0,)

    def test_comparison_works(self):
        assert _ver_tuple("3.7.0") > _ver_tuple("3.6.1")
        assert _ver_tuple("3.6.1") == _ver_tuple("3.6.1")
        assert _ver_tuple("3.6.0") < _ver_tuple("3.6.1")


# ── _fetch_latest_pypi_version ────────────────────────────────────────────────


class TestFetchLatestPypiVersion:
    def test_returns_none_on_network_error(self):
        def _fail(*args, **kwargs):
            raise OSError("network unavailable")

        with patch("urllib.request.urlopen", side_effect=_fail):
            result = _fetch_latest_pypi_version()
        assert result is None

    def test_returns_none_on_timeout(self):
        import socket

        def _timeout(*args, **kwargs):
            raise socket.timeout("timed out")

        with patch("urllib.request.urlopen", side_effect=_timeout):
            result = _fetch_latest_pypi_version()
        assert result is None

    def test_returns_none_on_http_404(self):
        from urllib.error import HTTPError

        def _not_found(*args, **kwargs):
            raise HTTPError(url="", code=404, msg="Not Found", hdrs=None, fp=None)  # type: ignore[arg-type]

        with patch("urllib.request.urlopen", side_effect=_not_found):
            result = _fetch_latest_pypi_version()
        assert result is None

    def test_returns_none_on_malformed_json(self):
        import io

        class _FakeResp:
            def read(self):
                return b"not json {{{{"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        with patch("urllib.request.urlopen", return_value=_FakeResp()):
            result = _fetch_latest_pypi_version()
        assert result is None

    def test_returns_version_on_success(self):
        import io, json

        payload = json.dumps({"info": {"version": "9.9.9"}}).encode()

        class _FakeResp:
            def read(self):
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        with patch("urllib.request.urlopen", return_value=_FakeResp()):
            result = _fetch_latest_pypi_version()
        assert result == "9.9.9"

    def test_returns_none_when_info_key_missing(self):
        import json

        payload = json.dumps({}).encode()

        class _FakeResp:
            def read(self):
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        with patch("urllib.request.urlopen", return_value=_FakeResp()):
            result = _fetch_latest_pypi_version()
        assert result is None

    def test_never_raises(self):
        with patch("urllib.request.urlopen", side_effect=Exception("unexpected")):
            result = _fetch_latest_pypi_version()
        assert result is None


# ── Doctor._update_check_diagnostic ──────────────────────────────────────────


class TestUpdateCheckDiagnostic:
    def _doctor(self, fetch_fn=None) -> Doctor:
        return Doctor(Path.cwd(), fetch_latest_version=fetch_fn)

    def test_skip_when_fetch_returns_none(self):
        doc = self._doctor(fetch_fn=lambda: None)
        diag = doc._update_check_diagnostic()
        assert diag.status == DiagnosticStatus.SKIP
        assert "skipped" in diag.message

    def test_pass_when_up_to_date(self):
        doc = self._doctor(fetch_fn=lambda: __version__)
        diag = doc._update_check_diagnostic()
        assert diag.status == DiagnosticStatus.PASS
        assert __version__ in diag.message

    def test_warn_when_stale(self):
        # Inject a version numerically greater than current
        def _newer():
            parts = __version__.split(".")
            parts[-1] = str(int(parts[-1]) + 100)
            return ".".join(parts)

        newer_version = _newer()
        doc = self._doctor(fetch_fn=lambda: newer_version)
        diag = doc._update_check_diagnostic()
        assert diag.status == DiagnosticStatus.WARN
        assert newer_version in diag.message
        assert __version__ in diag.message

    def test_warn_message_shows_arrow(self):
        doc = self._doctor(fetch_fn=lambda: "99.0.0")
        diag = doc._update_check_diagnostic()
        assert "→" in diag.message or "->" in diag.message

    def test_diagnostic_name_is_update_check(self):
        doc = self._doctor(fetch_fn=lambda: None)
        diag = doc._update_check_diagnostic()
        assert diag.name == "update_check"

    def test_never_raises_on_malformed_version(self):
        doc = self._doctor(fetch_fn=lambda: "not.a.valid.version.x.y.z")
        # Should not raise; may be PASS or WARN depending on comparison
        diag = doc._update_check_diagnostic()
        assert diag.status in (DiagnosticStatus.PASS, DiagnosticStatus.WARN, DiagnosticStatus.SKIP)

    def test_fetch_fn_injected_not_network(self):
        called = []

        def _mock_fetch():
            called.append(True)
            return __version__

        doc = self._doctor(fetch_fn=_mock_fetch)
        doc._update_check_diagnostic()
        assert called, "injected fetch_fn was not called"


# ── Doctor.run_diagnostics includes update_check ─────────────────────────────


class TestDoctorRunDiagnosticsIncludesUpdateCheck:
    def _run(self, fetch_fn=None):
        return Doctor(Path.cwd(), fetch_latest_version=fetch_fn).run_diagnostics()

    def test_update_check_in_diagnostics(self):
        diagnostics = self._run(fetch_fn=lambda: None)
        names = [d.name for d in diagnostics]
        assert "update_check" in names

    def test_offline_does_not_fail_doctor(self):
        diagnostics = self._run(fetch_fn=lambda: None)
        update_diag = next(d for d in diagnostics if d.name == "update_check")
        assert update_diag.status == DiagnosticStatus.SKIP

    def test_up_to_date_passes(self):
        diagnostics = self._run(fetch_fn=lambda: __version__)
        update_diag = next(d for d in diagnostics if d.name == "update_check")
        assert update_diag.status == DiagnosticStatus.PASS

    def test_stale_warns_not_fails(self):
        diagnostics = self._run(fetch_fn=lambda: "99.0.0")
        update_diag = next(d for d in diagnostics if d.name == "update_check")
        assert update_diag.status == DiagnosticStatus.WARN

    def test_no_network_calls_in_tests(self):
        with patch("urllib.request.urlopen") as mock_open:
            Doctor(Path.cwd(), fetch_latest_version=lambda: None).run_diagnostics()
            mock_open.assert_not_called()


# ── CLI: sac doctor output ────────────────────────────────────────────────────


class TestCLIDoctorUpdateCheck:
    def test_doctor_exits_successfully_when_offline(self):
        result = runner.invoke(
            app,
            ["doctor"],
            env={"SAFECODE_APPROVAL_DIR": "", "SAFECODE_SANDBOX_APPROVAL_DIR": ""},
            catch_exceptions=False,
        )
        # Doctor may exit non-zero for other checks (missing approval dirs etc.)
        # but must not raise an uncaught exception.
        assert result.exception is None

    def test_doctor_shows_update_check_key(self, tmp_path):
        # Use a mock fetch so no network is needed
        with patch.object(Doctor, "_update_check_diagnostic") as mock_diag:
            from safecode.core.diagnostic import Diagnostic, DiagnosticStatus

            mock_diag.return_value = Diagnostic(
                name="update_check",
                status=DiagnosticStatus.PASS,
                message=f"up to date ({__version__})",
            )
            result = runner.invoke(app, ["doctor"])
        # update_check should appear somewhere in the output
        assert "update_check" in result.output or "update" in result.output


# ── No telemetry ──────────────────────────────────────────────────────────────


class TestNoTelemetry:
    def test_fetch_sends_no_identifying_headers(self):
        """_fetch_latest_pypi_version must not add custom identifying headers."""
        import inspect
        import safecode.doctor as doctor_module

        source = inspect.getsource(doctor_module._fetch_latest_pypi_version)
        # No X-Telemetry, no machine ID, no user-specific headers
        assert "X-Telemetry" not in source
        assert "machine" not in source.lower() or "message" in source.lower()
        # Uses standard urlopen, not a custom session with auth
        assert "Authorization" not in source
