"""Tests for the v5.6.2 golden demo project."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
_DEMO_DIR = _ROOT / "examples" / "golden-demo"
_DEMO_FIXTURE_SRC = _DEMO_DIR / "src" / "calculator.py"
_DEMO_FIXTURE_TEST = _DEMO_DIR / "tests" / "test_calculator.py"
_DEMO_SCRIPT = _DEMO_DIR / "demo" / "run-demo.sh"
_DEMO_TRANSCRIPT = _DEMO_DIR / "demo" / "expected-transcript.md"
_PORTFOLIO_DOC = _ROOT / "docs" / "demo" / "portfolio-demo.md"
_README = _ROOT / "README.md"


def test_demo_directory_exists():
    assert _DEMO_DIR.is_dir()


def test_demo_fixture_source_exists():
    assert _DEMO_FIXTURE_SRC.exists()


def test_demo_fixture_source_has_bug():
    """The demo fixture must contain the deliberate bug (a + b instead of a - b)."""
    text = _DEMO_FIXTURE_SRC.read_text()
    assert "return a + b" in text
    assert "subtract" in text


def test_demo_fixture_test_exists():
    assert _DEMO_FIXTURE_TEST.exists()


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
    def test_demo_script_exists(self):
        assert _DEMO_SCRIPT.exists()

    def test_demo_script_is_executable(self):
        assert os.access(str(_DEMO_SCRIPT), os.X_OK)

    def test_demo_script_contains_mock_mode(self):
        text = _DEMO_SCRIPT.read_text()
        assert "mock" in text.lower()


class TestExpectedTranscript:
    def test_transcript_exists(self):
        assert _DEMO_TRANSCRIPT.exists()

    def test_transcript_contains_diff_preview(self):
        text = _DEMO_TRANSCRIPT.read_text()
        assert "diff" in text.lower() or "patch proposal" in text.lower()

    def test_transcript_contains_checkpoint(self):
        text = _DEMO_TRANSCRIPT.read_text()
        assert "checkpoint" in text.lower()

    def test_transcript_contains_audit(self):
        text = _DEMO_TRANSCRIPT.read_text()
        assert "audit" in text.lower()

    def test_transcript_contains_test_pass(self):
        text = _DEMO_TRANSCRIPT.read_text()
        assert "passed" in text.lower()

    def test_transcript_contains_rollback_evidence(self):
        text = _DEMO_TRANSCRIPT.read_text()
        assert "rollback" in text.lower()

    def test_transcript_contains_commit_offer(self):
        text = _DEMO_TRANSCRIPT.read_text()
        assert "commit" in text.lower()


class TestPortfolioDoc:
    def test_portfolio_doc_exists(self):
        assert _PORTFOLIO_DOC.exists()

    def test_portfolio_doc_contains_safety_gates(self):
        text = _PORTFOLIO_DOC.read_text()
        for word in ["checkpoint", "approval", "audit", "rollback", "diff"]:
            assert word in text.lower(), f"Portfolio doc missing {word!r}"

    def test_portfolio_doc_lists_key_source_files(self):
        text = _PORTFOLIO_DOC.read_text()
        assert "src/safecode/agent/orchestrator.py" in text
        assert "src/safecode/agent/prompts.py" in text


class TestReadmeLinks:
    def test_readme_links_golden_demo(self):
        text = _README.read_text()
        assert "golden-demo" in text

    def test_readme_links_portfolio_demo_doc(self):
        text = _README.read_text()
        assert "portfolio-demo.md" in text

    def test_readme_safety_loop_visible(self):
        text = _README.read_text()
        assert "checkpoint" in text.lower()
        assert "rollback" in text.lower()
