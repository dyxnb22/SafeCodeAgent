"""Homebrew formula status tests (v5.8.2).

Homebrew is not a production distribution channel for SafeCode Agent.
PyPI (pipx) is the only required production install path.
The Formula/ directory and scripts/update-brew-formula.sh are preserved
as historical artifacts showing the project is formula-ready.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SCRIPTS_DIR = Path("scripts")
UPDATE_BREW_SCRIPT = SCRIPTS_DIR / "update-brew-formula.sh"
FORMULA_DIR = Path("Formula")


class TestHomebrewNotPrimaryChannel:
    """Verify docs no longer present Homebrew as a required production path."""

    def _install_doc(self) -> str:
        return (Path(__file__).parent.parent / "docs" / "install-update.md").read_text(encoding="utf-8")

    def _readme(self) -> str:
        return (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")

    def test_install_doc_does_not_recommend_brew_in_matrix(self):
        """Install matrix must not list Homebrew as a recommended row."""
        text = self._install_doc()
        # The matrix section should not have a brew install row any more
        matrix_start = text.find("## Install Matrix")
        matrix_end = text.find("### PyPI Install", matrix_start) if matrix_start >= 0 else -1
        if matrix_start >= 0 and matrix_end >= 0:
            matrix_section = text[matrix_start:matrix_end]
            assert "brew install" not in matrix_section, (
                "Homebrew must not appear as a row in the Install Matrix"
            )

    def test_readme_brew_is_not_recommended(self):
        """README must not mark Homebrew as the recommended install path."""
        text = self._readme()
        # Check that any brew install line is not in a 'recommended' context
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if "brew install" in line or "brew tap" in line:
                context = "\n".join(lines[max(0, i - 3) : i + 3]).lower()
                assert "recommended" not in context, (
                    f"Homebrew presented as recommended: {line!r}"
                )

    def test_pypi_is_primary_install_method(self):
        assert "pipx install safecode-agent" in self._install_doc()
        assert "pipx install safecode-agent" in self._readme()


class TestFormulaArtifactPreserved:
    """Formula/ exists as a historical artifact showing formula-readiness."""

    def test_formula_file_exists(self):
        """Formula/safecode-agent.rb is preserved for portfolio evidence."""
        formula = FORMULA_DIR / "safecode-agent.rb"
        assert formula.exists(), (
            "Formula/safecode-agent.rb should be preserved as a portfolio artifact"
        )

    def test_update_brew_script_exists(self):
        """scripts/update-brew-formula.sh is preserved as release tooling."""
        assert UPDATE_BREW_SCRIPT.is_file(), (
            "scripts/update-brew-formula.sh should be preserved as release tooling"
        )

    def test_update_brew_flag_exists_in_cli(self):
        """--update-brew flag is available in sac release publish (hidden release tooling)."""
        from typer.testing import CliRunner
        from safecode.cli_ops import release_app

        runner = CliRunner()
        result = runner.invoke(release_app, ["publish", "--help"])
        assert "--update-brew" in result.output
