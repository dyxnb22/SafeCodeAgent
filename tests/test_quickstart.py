"""Tests for sac quickstart command (v2.7.5)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.cli_quickstart import run_quickstart

runner = CliRunner()


def test_quickstart_yes_exits_zero_in_fresh_repo(tmp_path: Path) -> None:
    result = runner.invoke(app, ["quickstart", "--yes"], catch_exceptions=False)
    assert result.exit_code == 0


def test_quickstart_creates_config_in_fresh_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["quickstart", "--yes"], catch_exceptions=False)
    assert result.exit_code == 0
    assert (tmp_path / ".sac" / "config.toml").exists()


def test_quickstart_does_not_overwrite_existing_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".sac" / "config.toml"
    config_path.parent.mkdir(parents=True)
    original = 'policy = "strict"\n'
    config_path.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["quickstart", "--yes"], catch_exceptions=False)
    assert result.exit_code == 0
    # Content must be unchanged — quickstart must not overwrite without --force.
    assert config_path.read_text(encoding="utf-8") == original


def test_quickstart_force_overwrites_existing_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".sac" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('policy = "strict"\n', encoding="utf-8")

    result = runner.invoke(app, ["quickstart", "--yes", "--force"], catch_exceptions=False)
    assert result.exit_code == 0
    # After --force, config should be a valid SafeCode config (not the stub).
    text = config_path.read_text(encoding="utf-8")
    assert "provider" in text


def test_quickstart_output_does_not_claim_edit_or_apply_ran(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Output must list next steps as commands to run, not assert they already ran."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["quickstart", "--yes"], catch_exceptions=False)
    assert result.exit_code == 0
    out = result.output
    # Must mention next-step commands as suggestions.
    assert "sac ask" in out
    assert "sac edit" in out
    assert "sac apply" in out
    assert "sac rollback" in out
    # Must NOT claim the edit was already done.
    assert "Applied" not in out
    assert "Patched" not in out
    assert "Wrote" not in out


def test_quickstart_demo_flag_materializes_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    demo_dest = tmp_path / "demo-out"
    result = runner.invoke(
        app,
        ["quickstart", "--yes", "--demo", "--demo-dest", str(demo_dest)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # At least one demo workflow directory should exist under demo-dest.
    assert demo_dest.exists()
    children = list(demo_dest.iterdir())
    assert len(children) >= 1


def test_quickstart_demo_flag_does_not_fail_if_already_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    demo_dest = tmp_path / "demo-out"
    # First call materializes.
    runner.invoke(app, ["quickstart", "--yes", "--demo", "--demo-dest", str(demo_dest)])
    # Second call without --force should not crash.
    result = runner.invoke(
        app,
        ["quickstart", "--yes", "--demo", "--demo-dest", str(demo_dest)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_run_quickstart_returns_zero(tmp_path: Path) -> None:
    code = run_quickstart(tmp_path, yes=True)
    assert code == 0
