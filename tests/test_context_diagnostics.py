"""Tests for diagnostics-aware context injection."""

from pathlib import Path

from typer.testing import CliRunner

from safecode.cli import app
from safecode.config import SafeCodeConfig
from safecode.context.collector import ContextCollector
from safecode.context.diagnostics import collect_diagnostics, diagnostics_context_block


def test_collects_python_pytest_diagnostics(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo():\n    assert 1 == 2\n",
        encoding="utf-8",
    )

    results = collect_diagnostics(tmp_path, SafeCodeConfig(), timeout_seconds=5)

    assert [result.name for result in results] == ["pytest"]
    assert results[0].executed is True
    assert results[0].exit_code != 0
    assert "assert 1 == 2" in results[0].output


def test_diagnostics_context_block_has_summary(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text("x = 1\n", encoding="utf-8")

    block = diagnostics_context_block(tmp_path, SafeCodeConfig())

    assert "summary" in block
    assert "results" in block
    assert block["summary"]["count"] >= 1


def test_context_collector_injects_diagnostics_when_enabled(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text("x = 1\n", encoding="utf-8")

    context = ContextCollector(tmp_path, SafeCodeConfig()).collect(include_diagnostics=True)

    assert "diagnostics" in context
    assert context["diagnostics"]["summary"]["count"] >= 1


def test_context_diagnostics_cli(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text("x = 1\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["context", "diagnostics", "--root", str(tmp_path), "--timeout-seconds", "5"],
    )

    assert result.exit_code == 0
    assert "SafeCode Diagnostics Context" in result.output
