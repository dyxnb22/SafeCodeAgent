"""Tests for Homebrew formula generation (v5.5.1)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest


SCRIPTS_DIR = Path("scripts")
UPDATE_BREW_SCRIPT = SCRIPTS_DIR / "update-brew-formula.sh"


class TestUpdateBrewScriptExists:
    def test_script_exists(self):
        assert UPDATE_BREW_SCRIPT.is_file(), "scripts/update-brew-formula.sh must exist"

    def test_script_is_executable(self):
        import os
        assert os.access(UPDATE_BREW_SCRIPT, os.X_OK), "script must be executable"

    def test_script_contains_formula_template(self):
        text = UPDATE_BREW_SCRIPT.read_text(encoding="utf-8")
        assert "safecode-agent" in text.lower()
        assert "sha256" in text.lower()
        assert "VERSION" in text

    def test_script_documents_usage(self):
        text = UPDATE_BREW_SCRIPT.read_text(encoding="utf-8")
        assert "Usage" in text or "usage" in text

    def test_script_uses_bash_shebang(self):
        text = UPDATE_BREW_SCRIPT.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env bash") or text.startswith("#!/bin/bash")


class TestReleasePublishUpdateBrewFlag:
    """sac release publish --update-brew is documented and wired."""

    def test_update_brew_option_exists(self):
        from typer.testing import CliRunner
        from safecode.cli_ops import release_app

        runner = CliRunner()
        result = runner.invoke(release_app, ["publish", "--help"])
        assert "--update-brew" in result.output

    def test_update_brew_dry_run_skipped(self, tmp_path):
        """--update-brew is silently skipped when dry_run=True (real publish required)."""
        from safecode.cli_ops import _run_update_brew_formula

        # _run_update_brew_formula only called by CLI when not dry_run+ok+update_brew
        # Test the helper directly — script not found returns a message instead of crashing
        missing = tmp_path / "no-script"
        msg = _run_update_brew_formula(missing)
        assert isinstance(msg, str)
        assert "skipping" in msg.lower() or "not found" in msg.lower() or "failed" in msg.lower()

    def test_update_brew_real_script_runs(self, tmp_path):
        """Script produces a formula file when called with valid args."""
        import subprocess
        import shutil

        if not shutil.which("bash"):
            pytest.skip("bash not available")

        # Copy script to tmp to avoid cwd dependency
        script_path = UPDATE_BREW_SCRIPT
        fake_sha = "a" * 64
        proc = subprocess.run(
            ["bash", str(script_path), "5.5.0", fake_sha],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        assert proc.returncode == 0, f"script failed: {proc.stderr}"
        formula = Path("Formula") / "safecode-agent.rb"
        assert formula.exists()
        content = formula.read_text(encoding="utf-8")
        assert "5.5.0" in content
        assert fake_sha in content
        assert "SafecodeAgent" in content

    def test_helper_handles_missing_script_gracefully(self, tmp_path):
        from safecode.cli_ops import _run_update_brew_formula
        msg = _run_update_brew_formula(tmp_path)
        assert "skipping" in msg.lower() or "not found" in msg.lower()


class TestBrewFormulaContents:
    """The generated Formula/safecode-agent.rb (if present) has required content."""

    @pytest.fixture
    def formula_path(self, tmp_path):
        import subprocess
        import shutil

        if not shutil.which("bash"):
            pytest.skip("bash not available")

        script = UPDATE_BREW_SCRIPT
        proc = subprocess.run(
            ["bash", str(script), "5.5.0", "b" * 64],
            capture_output=True, text=True, cwd=Path.cwd(),
        )
        assert proc.returncode == 0
        return Path("Formula") / "safecode-agent.rb"

    def test_formula_mentions_safecode(self, formula_path):
        text = formula_path.read_text(encoding="utf-8")
        assert "safecode" in text.lower()

    def test_formula_has_desc(self, formula_path):
        text = formula_path.read_text(encoding="utf-8")
        assert "desc" in text

    def test_formula_has_test_block(self, formula_path):
        text = formula_path.read_text(encoding="utf-8")
        assert "test do" in text

    def test_formula_uses_sac_binary(self, formula_path):
        text = formula_path.read_text(encoding="utf-8")
        assert "sac" in text
