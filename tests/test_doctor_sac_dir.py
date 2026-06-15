"""Tests for v4.25.1: B14 doctor sac_dir_writable and disk_space diagnostics."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from safecode.core.diagnostic import DiagnosticStatus
from safecode.doctor import Doctor


def _make_doctor(tmp_path: Path) -> Doctor:
    return Doctor(tmp_path)


# ---------------------------------------------------------------------------
# B14: sac_dir_writable diagnostic
# ---------------------------------------------------------------------------

class TestSacDirWritable:
    def test_pass_when_sac_dir_is_writable(self, tmp_path):
        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        doctor = _make_doctor(tmp_path)
        diagnostics = doctor._sac_dir_diagnostics()
        writable_diag = next(d for d in diagnostics if d.name == "sac_dir_writable")
        assert writable_diag.status == DiagnosticStatus.PASS

    def test_fail_when_probe_raises_permission_error(self, tmp_path):
        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        doctor = _make_doctor(tmp_path)

        with patch("pathlib.Path.touch", side_effect=PermissionError("no write")):
            diagnostics = doctor._sac_dir_diagnostics()

        writable_diag = next(d for d in diagnostics if d.name == "sac_dir_writable")
        assert writable_diag.status == DiagnosticStatus.FAIL
        assert "writable" in writable_diag.message.lower() or "not writable" in writable_diag.message.lower()

    def test_fail_message_includes_next_step_hint(self, tmp_path):
        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        doctor = _make_doctor(tmp_path)

        with patch("pathlib.Path.touch", side_effect=PermissionError("no write")):
            diagnostics = doctor._sac_dir_diagnostics()

        writable_diag = next(d for d in diagnostics if d.name == "sac_dir_writable")
        assert writable_diag.hints, "Expected hints for writable FAIL"
        assert any("sac/" in h or "permission" in h.lower() for h in writable_diag.hints)

    def test_sac_dir_created_if_missing(self, tmp_path):
        """_sac_dir_diagnostics creates .sac/ if it doesn't exist."""
        doctor = _make_doctor(tmp_path)
        assert not (tmp_path / ".sac").exists()
        doctor._sac_dir_diagnostics()
        assert (tmp_path / ".sac").exists()


# ---------------------------------------------------------------------------
# B14: disk_space diagnostic
# ---------------------------------------------------------------------------

class TestDiskSpace:
    def test_pass_when_plenty_of_space(self, tmp_path):
        doctor = _make_doctor(tmp_path)
        fake_usage = MagicMock()
        fake_usage.free = 10 * 1024 * 1024 * 1024  # 10 GB
        with patch("shutil.disk_usage", return_value=fake_usage):
            diagnostics = doctor._sac_dir_diagnostics()
        disk_diag = next(d for d in diagnostics if d.name == "disk_space")
        assert disk_diag.status == DiagnosticStatus.PASS

    def test_warn_when_less_than_100mb(self, tmp_path):
        """B14: WARN (not FAIL) when free space < 100 MB."""
        doctor = _make_doctor(tmp_path)
        fake_usage = MagicMock()
        fake_usage.free = 50 * 1024 * 1024  # 50 MB
        with patch("shutil.disk_usage", return_value=fake_usage):
            diagnostics = doctor._sac_dir_diagnostics()
        disk_diag = next(d for d in diagnostics if d.name == "disk_space")
        assert disk_diag.status == DiagnosticStatus.WARN
        assert "low disk" in disk_diag.message.lower() or "50" in disk_diag.message

    def test_skip_when_disk_usage_raises(self, tmp_path):
        doctor = _make_doctor(tmp_path)
        with patch("shutil.disk_usage", side_effect=OSError("no disk info")):
            diagnostics = doctor._sac_dir_diagnostics()
        disk_diag = next(d for d in diagnostics if d.name == "disk_space")
        assert disk_diag.status == DiagnosticStatus.SKIP

    def test_run_diagnostics_includes_sac_dir_checks(self, tmp_path):
        """run_diagnostics() includes sac_dir_writable and disk_space."""
        doctor = _make_doctor(tmp_path)
        diagnostics = doctor.run_diagnostics()
        names = {d.name for d in diagnostics}
        assert "sac_dir_writable" in names
        assert "disk_space" in names
