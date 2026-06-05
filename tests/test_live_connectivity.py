"""Tests for v4.17.2 live connectivity diagnostics (--live flag)."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from safecode.core.diagnostic import Diagnostic, DiagnosticStatus
from safecode.doctor import Doctor


def test_live_provider_ping_offline_mode():
    """Ping returns SKIP when SAFECODE_DOCTOR_UPDATE_CHECK=0."""
    with patch.dict(os.environ, {"SAFECODE_DOCTOR_UPDATE_CHECK": "0"}):
        result = Doctor._live_provider_ping("https://api.deepseek.com")
    assert result.status == DiagnosticStatus.SKIP
    assert "offline" in result.message.lower()


def test_live_provider_ping_empty_url():
    """Ping returns SKIP when base_url is empty."""
    result = Doctor._live_provider_ping("")
    assert result.status == DiagnosticStatus.SKIP
    assert "no base url" in result.message.lower()


def test_live_provider_ping_success():
    """Ping returns PASS on successful HTTP response."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value.status = 200
        result = Doctor._live_provider_ping("https://api.example.com")
    assert result.status == DiagnosticStatus.PASS
    assert "reachable" in result.message


def test_live_provider_ping_failure():
    """Ping returns FAIL on connection error."""
    with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
        result = Doctor._live_provider_ping("https://api.example.com")
    assert result.status == DiagnosticStatus.FAIL
    assert "unreachable" in result.message
    assert result.hints


def test_doctor_run_diagnostics_includes_live_when_requested():
    """Doctor.run_diagnostics includes connectivity ping when live=True."""
    doc = Doctor(Path("/tmp"))
    diagnostics = doc.run_diagnostics(live=True)
    names = [d.name for d in diagnostics]
    assert "provider_connectivity" in names


def test_doctor_run_diagnostics_excludes_live_by_default():
    """Doctor.run_diagnostics excludes connectivity ping when live=False (default)."""
    doc = Doctor(Path("/tmp"))
    diagnostics = doc.run_diagnostics(live=False)
    names = [d.name for d in diagnostics]
    assert "provider_connectivity" not in names


def test_live_ping_respects_timeout():
    """Ping uses configurable timeout."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value.status = 200
        result = Doctor._live_provider_ping("https://api.example.com", timeout=3)
    assert result.status == DiagnosticStatus.PASS
