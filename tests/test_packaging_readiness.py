"""Packaging readiness checks for the source checkout."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_package_verifier_script_exists() -> None:
    script = ROOT / "scripts" / "verify-package.py"
    assert script.exists()
    assert "REQUIRED_WHEEL_MEMBERS" in script.read_text(encoding="utf-8")


def test_packaging_inputs_are_present() -> None:
    namespace = runpy.run_path(str(ROOT / "scripts" / "verify-package.py"), run_name="verify_package")
    required = namespace["REQUIRED_SOURCE_FILES"]
    missing = [path for path in required if not (ROOT / path).exists()]
    assert missing == []


def test_pyproject_sdist_includes_docs_and_examples() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.hatch.build.targets.sdist]" in text
    assert '"docs"' in text
    assert '"examples"' in text
    assert '"src/safecode"' in text
