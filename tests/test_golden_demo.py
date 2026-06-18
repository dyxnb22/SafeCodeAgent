"""Tests for the v5.6.2 golden demo project."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]

_ROOT = Path(__file__).parent.parent
_DEMO_DIR = _ROOT / "examples" / "golden-demo"
_DEMO_FIXTURE_SRC = _DEMO_DIR / "src" / "calculator.py"
_DEMO_FIXTURE_TEST = _DEMO_DIR / "tests" / "test_calculator.py"
_DEMO_SCRIPT = _DEMO_DIR / "demo" / "run-demo.sh"
_DEMO_TRANSCRIPT = _DEMO_DIR / "demo" / "expected-transcript.md"
_README = _ROOT / "README.md"


def test_demo_core_files_exist():
    assert _DEMO_DIR.is_dir()
    assert _DEMO_FIXTURE_SRC.exists()
    assert _DEMO_FIXTURE_TEST.exists()
    assert _DEMO_SCRIPT.exists()
    assert _DEMO_TRANSCRIPT.exists()


def test_demo_fixture_source_has_bug():
    """The demo fixture must contain the deliberate bug (a + b instead of a - b)."""
    text = _DEMO_FIXTURE_SRC.read_text()
    assert "return a + b" in text
    assert "subtract" in text


class TestDemoFixtureIsBrokenThenFixable:
    def test_fixture_starts_failing(self):
        """The test_subtract test must fail with the buggy implementation."""
        result = subprocess.run(
            ["python3", "-m", "pytest", str(_DEMO_FIXTURE_TEST), "-q", "--no-header"],
            capture_output=True, text=True, cwd=str(_DEMO_DIR),
        )
        assert result.returncode != 0, "Fixture should start with a failing test"

    def test_fixture_can_pass_after_fix(self):
        """Copy both src and tests to a temp dir, apply the fix, run pytest."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            shutil.copytree(str(_DEMO_DIR / "src"), str(tmpdir / "src"))
            shutil.copytree(str(_DEMO_DIR / "tests"), str(tmpdir / "tests"))
            calc = tmpdir / "src" / "calculator.py"
            text = calc.read_text()
            text = text.replace("return a + b  # BUG: should be a - b", "return a - b")
            calc.write_text(text)

            result = subprocess.run(
                ["python3", "-m", "pytest", "tests/", "-q", "--no-header"],
                capture_output=True, text=True, cwd=str(tmpdir),
            )
            assert result.returncode == 0, (
                f"After fix, tests should pass. stderr={result.stderr}"
            )


class TestDemoScript:
    def test_demo_script_is_executable(self):
        assert os.access(str(_DEMO_SCRIPT), os.X_OK)

    def test_demo_script_contains_mock_mode(self):
        text = _DEMO_SCRIPT.read_text()
        assert "mock" in text.lower()


class TestExpectedTranscript:
    def test_transcript_contains_expected_flow_markers(self):
        text = _DEMO_TRANSCRIPT.read_text()
        for marker in ("checkpoint", "audit", "passed", "rollback", "commit"):
            assert marker in text.lower()
        assert "diff" in text.lower() or "patch proposal" in text.lower()


class TestReadmeLinks:
    def test_readme_links_enterprise_planning_and_safety_invariants(self):
        text = _README.read_text()
        assert "product-planning/README.md" in text
        assert "enterprise-docs/architecture.md" in text
        assert "model output is never execution authority" in text.lower()
        assert "policy-gated" in text.lower()
