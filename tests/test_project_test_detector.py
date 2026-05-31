"""Project test detection and run tests for v2.0.3."""

from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from safecode.cli import app
from safecode.config import SafeCodeConfig
from safecode.project.test_detector import ProjectTestDetector
from safecode.shell.runner import ShellRunner


runner = CliRunner()


def test_detects_pytest_and_uv_candidates(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["pytest"]\n',
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir()

    commands = [candidate.command for candidate in ProjectTestDetector(tmp_path).detect()]

    assert commands == ["uv run pytest -q", "pytest -q"]


def test_detects_npm_test_script(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest run"}}',
        encoding="utf-8",
    )

    candidates = ProjectTestDetector(tmp_path).detect()

    assert len(candidates) == 1
    assert candidates[0].command == "npm test"
    assert candidates[0].tool == "npm"


def test_detects_pnpm_when_lockfile_exists(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest run"}}',
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")

    assert ProjectTestDetector(tmp_path).detect()[0].command == "pnpm test"


def test_detected_commands_are_proposed_through_policy(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()

    proposal = ShellRunner(tmp_path, SafeCodeConfig()).propose("pytest -q")

    assert proposal.status == "blocked"
    assert "not allowlisted" in proposal.decision.reason


def test_cli_test_detect_renders_policy_status(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "tests").mkdir()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["test", "detect"])

    assert result.exit_code == 0
    assert "pytest -q" in result.stdout
    assert "blocked" in result.stdout


def test_cli_test_run_uses_shell_runner_when_policy_allows(tmp_path: Path, monkeypatch) -> None:
    user_config = tmp_path / "user-config.toml"
    user_config.write_text(
        '[shell]\nallowed_commands = ["pytest"]\nrequire_confirm_for_medium = false\n',
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="tests passed\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["test", "run", "--command", "pytest -q", "--yes"])

    assert result.exit_code == 0
    assert "tests passed" in result.stdout


def test_cli_test_run_prefers_policy_runnable_detected_candidate(tmp_path: Path, monkeypatch) -> None:
    user_config = tmp_path / "user-config.toml"
    user_config.write_text(
        '[shell]\nallowed_commands = ["pytest"]\nrequire_confirm_for_medium = false\n',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["pytest"]\n', encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="selected pytest\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = runner.invoke(app, ["test", "run", "--yes"])

    assert result.exit_code == 0
    assert "Command: pytest -q" in result.stdout
    assert "selected pytest" in result.stdout
