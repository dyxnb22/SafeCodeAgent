"""Tests for sac quickstart command (v2.7.5 / v3.7.0)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.cli_quickstart import _detect_stack, run_quickstart

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


# ---------------------------------------------------------------------------
# v3.7.0 stack-aware quickstart tests
# ---------------------------------------------------------------------------

class TestDetectStack:
    def test_detects_python_via_pyproject_toml(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\n', encoding="utf-8")
        assert _detect_stack(tmp_path) == "python"

    def test_detects_typescript_via_package_json(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
        assert _detect_stack(tmp_path) == "typescript"

    def test_detects_go_via_go_mod(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
        assert _detect_stack(tmp_path) == "go"

    def test_detects_rust_via_cargo_toml(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname="x"\n', encoding="utf-8")
        assert _detect_stack(tmp_path) == "rust"

    def test_unknown_when_no_manifest(self, tmp_path: Path) -> None:
        assert _detect_stack(tmp_path) == "unknown"

    def test_python_takes_priority_over_others(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\n', encoding="utf-8")
        (tmp_path / "package.json").write_text('{}', encoding="utf-8")
        # Python manifest file checked first
        assert _detect_stack(tmp_path) == "python"


class TestStackAwareQuickstart:
    def test_python_stack_mentions_sac_fix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        result = runner.invoke(app, ["quickstart", "--yes"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "sac fix" in result.output

    def test_typescript_stack_shows_npm_test(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
        result = runner.invoke(app, ["quickstart", "--yes"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "npm test" in result.output

    def test_go_stack_shows_go_test(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
        result = runner.invoke(app, ["quickstart", "--yes"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "go test" in result.output

    def test_rust_stack_shows_cargo_test(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "Cargo.toml").write_text('[package]\n', encoding="utf-8")
        result = runner.invoke(app, ["quickstart", "--yes"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "cargo test" in result.output

    def test_unknown_stack_preserves_existing_behavior(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["quickstart", "--yes"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "sac ask" in result.output
        assert "sac edit" in result.output
