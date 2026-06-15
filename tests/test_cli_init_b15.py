"""Tests for v4.25.1: B15 sac init live connectivity check."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from safecode.cli_init import _init_live_connectivity_check
from safecode.core.diagnostic import Diagnostic, DiagnosticStatus


# Patch target: Doctor is imported locally in _init_live_connectivity_check
_DOCTOR_PATCH = "safecode.doctor.Doctor"


def _make_pass_diag(name: str = "provider_connectivity") -> Diagnostic:
    return Diagnostic(name=name, status=DiagnosticStatus.PASS, message="ok")


def _make_fail_diag(name: str = "provider_connectivity") -> Diagnostic:
    return Diagnostic(name=name, status=DiagnosticStatus.FAIL, message="unreachable")


def _make_skip_diag(name: str = "provider_connectivity") -> Diagnostic:
    return Diagnostic(name=name, status=DiagnosticStatus.SKIP, message="no key")


# ---------------------------------------------------------------------------
# _init_live_connectivity_check
# ---------------------------------------------------------------------------

class TestInitLiveConnectivityCheck:
    def test_prints_reachable_on_pass(self):
        """B15: prints 'Provider API reachable' when ping passes."""
        console_obj = MagicMock()
        with patch(_DOCTOR_PATCH) as MockDoctor:
            MockDoctor._live_provider_ping.return_value = _make_pass_diag()
            MockDoctor._live_anthropic_ping.return_value = _make_pass_diag()
            _init_live_connectivity_check("openai", "sk-test", console_obj)
        printed = " ".join(str(c) for c in console_obj.print.call_args_list)
        assert "reachable" in printed.lower()

    def test_prints_warning_on_fail(self):
        """B15: prints yellow warning when ping fails."""
        console_obj = MagicMock()
        with patch(_DOCTOR_PATCH) as MockDoctor:
            MockDoctor._live_provider_ping.return_value = _make_fail_diag()
            _init_live_connectivity_check("openai", "sk-bad", console_obj)
        printed = " ".join(str(c) for c in console_obj.print.call_args_list)
        assert "warning" in printed.lower() or "could not reach" in printed.lower()

    def test_anthropic_uses_live_anthropic_ping(self):
        """B15: Anthropic provider uses _live_anthropic_ping."""
        console_obj = MagicMock()
        with patch(_DOCTOR_PATCH) as MockDoctor:
            MockDoctor._live_anthropic_ping.return_value = _make_pass_diag("anthropic_connectivity")
            _init_live_connectivity_check("anthropic", "sk-ant-test", console_obj)
            MockDoctor._live_anthropic_ping.assert_called_once_with("sk-ant-test")

    def test_openai_uses_live_provider_ping(self):
        """B15: OpenAI-compatible provider uses _live_provider_ping."""
        console_obj = MagicMock()
        with patch(_DOCTOR_PATCH) as MockDoctor:
            MockDoctor._live_provider_ping.return_value = _make_pass_diag()
            _init_live_connectivity_check("openai", "sk-openai-test", console_obj)
            MockDoctor._live_provider_ping.assert_called_once()

    def test_never_raises_on_exception(self):
        """B15: connectivity check never blocks init completion on error."""
        console_obj = MagicMock()
        with patch(_DOCTOR_PATCH, side_effect=RuntimeError("Doctor unavailable")):
            # Must not raise.
            _init_live_connectivity_check("openai", "sk-test", console_obj)

    def test_skip_diagnostic_suppresses_output(self):
        """B15: SKIP diagnostic (e.g. offline mode) suppresses reachable/warning output."""
        console_obj = MagicMock()
        with patch(_DOCTOR_PATCH) as MockDoctor:
            MockDoctor._live_provider_ping.return_value = _make_skip_diag()
            _init_live_connectivity_check("openai", "sk-test", console_obj)
        calls_text = " ".join(str(c) for c in console_obj.print.call_args_list)
        assert "reachable" not in calls_text.lower()
        assert "could not reach" not in calls_text.lower()

    def test_warning_includes_doctor_hint(self):
        """B15: failure warning mentions 'sac doctor --live'."""
        console_obj = MagicMock()
        with patch(_DOCTOR_PATCH) as MockDoctor:
            MockDoctor._live_provider_ping.return_value = _make_fail_diag()
            _init_live_connectivity_check("openai", "sk-bad", console_obj)
        printed = " ".join(str(c) for c in console_obj.print.call_args_list)
        assert "doctor" in printed.lower()
