"""Tests for v3.9.1 T-3.9.1-A: install docs correctness.

Verifies that docs/install-update.md documents the required install commands
from a fixture list. No live network calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_INSTALL_DOC = Path(__file__).parent.parent / "docs" / "install-update.md"

# Required install command fragments that must appear in the docs.
_REQUIRED_COMMANDS: list[tuple[str, str]] = [
    # (fragment, description)
    ("pipx install safecode-agent", "production pipx install command"),
    ("pipx install", "pipx install appears at all"),
    ("uv build", "offline wheel build command"),
    ("test.pypi.org", "TestPyPI URL documented"),
    ("--repository test-pypi", "TestPyPI rehearsal CLI flag"),
    ("SAFECODE_PUBLISH=1", "publish gate env var documented"),
    ("sac release publish", "publish command documented"),
    ("sac release preflight", "preflight command documented"),
    ("sac release bump", "bump command documented"),
    ("cosign", "cosign signing tool mentioned"),
    ("gpg", "gpg signing tool mentioned"),
    ("detach", "detached signature mechanism documented"),
]

# Required sections
_REQUIRED_SECTIONS: list[str] = [
    "Release Signing",
    "TestPyPI Rehearsal",
    "pipx",
]


def _load_doc() -> str:
    return _INSTALL_DOC.read_text(encoding="utf-8")


class TestInstallDocExists:
    def test_install_doc_exists(self):
        assert _INSTALL_DOC.exists(), f"docs/install-update.md not found at {_INSTALL_DOC}"

    def test_install_doc_is_nonempty(self):
        content = _load_doc()
        assert len(content) > 100


class TestRequiredInstallCommands:
    @pytest.mark.parametrize("fragment,description", _REQUIRED_COMMANDS)
    def test_command_present(self, fragment: str, description: str):
        content = _load_doc()
        assert fragment in content, (
            f"Expected docs/install-update.md to contain {fragment!r} ({description})"
        )


class TestRequiredSections:
    @pytest.mark.parametrize("section", _REQUIRED_SECTIONS)
    def test_section_present(self, section: str):
        content = _load_doc()
        assert section in content, (
            f"Expected docs/install-update.md to contain section {section!r}"
        )


class TestOfflineInstallRecipe:
    def test_offline_build_then_install(self):
        content = _load_doc()
        # offline recipe: build + install from local wheel
        assert "uv build" in content
        # must mention pipx install of a local wheel (not just from pypi)
        assert "dist/" in content or ".whl" in content

    def test_offline_recipe_mentions_pipx(self):
        content = _load_doc()
        assert "pipx install" in content


class TestBrewStrategy:
    def test_brew_strategy_is_documented(self):
        """Brew strategy (tap/formula/defer) must be documented somewhere."""
        install_doc = _load_doc()
        versioning_policy = (
            Path(__file__).parent.parent / "docs" / "versioning-policy.md"
        ).read_text(encoding="utf-8")
        combined = install_doc + versioning_policy
        assert "brew" in combined.lower() or "homebrew" in combined.lower(), (
            "Brew strategy must be documented in install-update.md or versioning-policy.md"
        )


class TestTestPyPIRehearsalFlow:
    def test_test_pypi_rehearsal_dry_run_command(self):
        content = _load_doc()
        # Dry-run command for test-pypi
        assert "--repository test-pypi" in content

    def test_test_pypi_real_upload_command(self):
        content = _load_doc()
        assert "SAFECODE_PUBLISH=1" in content
        assert "test-pypi" in content

    def test_test_pypi_pipx_install_command(self):
        content = _load_doc()
        assert "test.pypi.org/simple" in content

    def test_production_pypi_command_present(self):
        content = _load_doc()
        # Production publish command
        assert "SAFECODE_PUBLISH=1" in content
        assert "--no-dry-run" in content
