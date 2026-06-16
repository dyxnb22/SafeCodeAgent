"""Tests for the realistic multi-file SafeCode demo."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]

_ROOT = Path(__file__).parent.parent
_DEMO = _ROOT / "examples" / "realistic-demo"
_SCRIPT = _DEMO / "demo" / "run-demo.sh"
_TRANSCRIPT = _DEMO / "demo" / "expected-transcript.md"


def test_realistic_demo_static_contract() -> None:
    assert (_DEMO / "src" / "todo_service" / "api.py").exists()
    assert (_DEMO / "src" / "todo_service" / "store.py").exists()
    assert (_DEMO / "tests" / "test_todo_service.py").exists()
    assert _TRANSCRIPT.exists()
    assert os.access(_SCRIPT, os.X_OK)
    text = _TRANSCRIPT.read_text()
    for marker in ["review boundary", "checkpoint", "audit", "rollback"]:
        assert marker in text.lower()


def test_realistic_demo_starts_failing() -> None:
    result = subprocess.run(
        ["python3", "-m", "pytest", "tests/test_todo_service.py", "-q"],
        cwd=_DEMO,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_realistic_demo_is_fixable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        shutil.copytree(_DEMO / "src", tmpdir / "src")
        shutil.copytree(_DEMO / "tests", tmpdir / "tests")
        store = tmpdir / "src" / "todo_service" / "store.py"
        text = store.read_text()
        text = text.replace("completed=True", "completed=False")
        text = text.replace(
            "return list(self._items)",
            "return [item for item in self._items if not item.completed]",
        )
        store.write_text(text)
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/test_todo_service.py", "-q"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "2 passed" in result.stdout


def test_realistic_demo_script_runs_to_green() -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "2 passed" in result.stdout
    assert "Checkpoint created" in result.stdout
