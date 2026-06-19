"""CLI tests for sac demo portfolio commands (v3.2.1-T1)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli_test_demo import demo_app

_ROOT = Path(__file__).resolve().parents[3]
_COMMAND = ("pr-review", "--offline")
_DEMO_RUN_DIR = _ROOT / ".sac" / "enterprise" / "runs" / "run-demoprreview"
_SHA256_LINE = re.compile(r"audit_chain_head: [a-f0-9]{64}")


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
    assert "audit_chain_head: generated" in output
    assert _SHA256_LINE.search(output) is None


def test_pr_review_requires_offline_flag(tmp_path: Path) -> None:
    root = _seed_demo_root(tmp_path)
    runner = CliRunner()
    result = runner.invoke(demo_app, ["pr-review", "--root", str(root)])
    assert result.exit_code == 1


def test_unknown_demo_command_fails() -> None:
    runner = CliRunner()
    result = runner.invoke(demo_app, ["unknown-demo", "--offline"])
    assert result.exit_code != 0


def test_pr_review_offline_demo_output_is_stable_across_runs(tmp_path: Path) -> None:
    root = _seed_demo_root(tmp_path)
    runner = CliRunner()
    outputs: list[str] = []
    for _ in range(2):
        result = runner.invoke(demo_app, [*_COMMAND, "--root", str(root)])
        assert result.exit_code == 0, result.stdout + result.stderr
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]


def test_pr_review_offline_demo_does_not_write_project_root_sac(tmp_path: Path) -> None:
    root = _seed_demo_root(tmp_path)
    runner = CliRunner()
    result = runner.invoke(demo_app, [*_COMMAND, "--root", str(root)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert not (root / ".sac" / "enterprise" / "runs" / "run-demoprreview").exists()


def test_pr_review_offline_demo_from_repo_root_does_not_touch_repo_sac(monkeypatch) -> None:
    monkeypatch.chdir(_ROOT)
    existed_before = _DEMO_RUN_DIR.exists()
    before_entries = (
        {path.name for path in _DEMO_RUN_DIR.iterdir()} if existed_before else set()
    )
    runner = CliRunner()
    result = runner.invoke(demo_app, list(_COMMAND))
    assert result.exit_code == 0, result.stdout + result.stderr
    if existed_before:
        assert {path.name for path in _DEMO_RUN_DIR.iterdir()} == before_entries
    else:
        assert not _DEMO_RUN_DIR.exists()


def test_pr_review_output_dir_writes_persistent_workspace(tmp_path: Path) -> None:
    root = _seed_demo_root(tmp_path)
    workspace = tmp_path / "demo-workspace"
    runner = CliRunner()
    result = runner.invoke(
        demo_app,
        [*_COMMAND, "--root", str(root), "--output-dir", str(workspace)],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert (workspace / ".sac" / "enterprise" / "runs" / "run-demoprreview").exists()
    assert not (root / ".sac" / "enterprise" / "runs" / "run-demoprreview").exists()


def test_pr_review_show_run_metadata_exposes_raw_audit_chain_head(tmp_path: Path) -> None:
    root = _seed_demo_root(tmp_path)
    workspace = tmp_path / "demo-workspace"
    runner = CliRunner()
    result = runner.invoke(
        demo_app,
        [
            *_COMMAND,
            "--root",
            str(root),
            "--output-dir",
            str(workspace),
            "--show-run-metadata",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert _SHA256_LINE.search(result.stdout) is not None
