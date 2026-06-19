"""CLI tests for sac demo portfolio commands (v3.2.1-T1)."""

from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli_test_demo import demo_app

_ROOT = Path(__file__).resolve().parents[3]
_COMMAND = ("pr-review", "--offline")


def _seed_demo_root(tmp_path: Path) -> Path:
    shutil.copytree(_ROOT / "examples" / "enterprise", tmp_path / "examples" / "enterprise")
    return tmp_path


def test_demo_list_includes_pr_review() -> None:
    runner = CliRunner()
    result = runner.invoke(demo_app, ["--list"])
    assert result.exit_code == 0
    assert "pr-review" in result.stdout


def test_pr_review_offline_demo_exits_zero(tmp_path: Path) -> None:
    root = _seed_demo_root(tmp_path)
    runner = CliRunner()
    result = runner.invoke(demo_app, [*_COMMAND, "--root", str(root)])
    assert result.exit_code == 0, result.stdout + result.stderr
    output = result.stdout
    assert "demo name: pr-review" in output
    assert "task_type: pr_review" in output
    assert "citation_id:" in output
    assert "workflow timeline" in output.lower() or "node: classify_request" in output
    assert "approval-gated action: refused" in output
    assert "audit_chain_head:" in output or "audit_summary:" in output


def test_pr_review_requires_offline_flag(tmp_path: Path) -> None:
    root = _seed_demo_root(tmp_path)
    runner = CliRunner()
    result = runner.invoke(demo_app, ["pr-review", "--root", str(root)])
    assert result.exit_code == 1


def test_unknown_demo_command_fails() -> None:
    runner = CliRunner()
    result = runner.invoke(demo_app, ["unknown-demo", "--offline"])
    assert result.exit_code != 0
