"""Tests for sac setup and sac setup --wizard (v2.3.1 / v3.7.1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app, run_setup_wizard
from safecode.setup import write_setup

runner = CliRunner()


# ---------------------------------------------------------------------------
# Existing v2.3.1 tests (preserved)
# ---------------------------------------------------------------------------

def test_write_setup_creates_config_and_env(tmp_path):
    result = write_setup(
        tmp_path,
        provider="mock",
        model="demo-model",
        policy="strict",
        approval_dir=tmp_path.parent / "approvals",
        sandbox_approval_dir=tmp_path.parent / "sandbox-approvals",
    )

    assert result.config_path.exists()
    assert result.env_path.exists()
    assert 'provider = "mock"' in result.config_path.read_text(encoding="utf-8")
    assert 'model = "demo-model"' in result.config_path.read_text(encoding="utf-8")
    assert 'policy = "strict"' in result.config_path.read_text(encoding="utf-8")
    assert "SAFECODE_APPROVAL_DIR" in result.env_path.read_text(encoding="utf-8")


def test_write_setup_rejects_invalid_policy(tmp_path):
    with pytest.raises(ValueError, match="policy"):
        write_setup(tmp_path, policy="reckless")


def test_write_setup_refuses_to_overwrite_without_force(tmp_path):
    write_setup(
        tmp_path,
        approval_dir=tmp_path.parent / "approvals",
        sandbox_approval_dir=tmp_path.parent / "sandbox-approvals",
    )
    with pytest.raises(FileExistsError):
        write_setup(
            tmp_path,
            approval_dir=tmp_path.parent / "approvals",
            sandbox_approval_dir=tmp_path.parent / "sandbox-approvals",
        )


def test_setup_cli_writes_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "setup",
            "--yes",
            "--provider",
            "mock",
            "--model",
            "demo",
            "--policy",
            "learning",
            "--approval-dir",
            str(tmp_path.parent / "approvals"),
            "--sandbox-approval-dir",
            str(tmp_path.parent / "sandbox-approvals"),
        ],
    )

    assert result.exit_code == 0
    assert "SafeCode Setup" in result.output
    assert (tmp_path / ".sac" / "config.toml").exists()
    assert (tmp_path / ".sac" / "setup.env").exists()


def test_setup_cli_rejects_second_run_without_force(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = [
        "setup",
        "--yes",
        "--approval-dir",
        str(tmp_path.parent / "approvals"),
        "--sandbox-approval-dir",
        str(tmp_path.parent / "sandbox-approvals"),
    ]
    assert runner.invoke(app, args).exit_code == 0
    result = runner.invoke(app, args)
    assert result.exit_code != 0
    assert "already exist" in result.output


# ---------------------------------------------------------------------------
# v3.7.1 wizard non-TTY tests
# ---------------------------------------------------------------------------

class TestWizardNonTTY:
    def test_non_tty_exits_zero(self, tmp_path: Path) -> None:
        code = run_setup_wizard(tmp_path, is_tty=False)
        assert code == 0

    def test_non_tty_does_not_write_config(self, tmp_path: Path) -> None:
        run_setup_wizard(tmp_path, is_tty=False)
        assert not (tmp_path / ".sac" / "config.toml").exists()

    def test_wizard_cli_non_tty_exits_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["setup", "--wizard"], catch_exceptions=False)
        assert result.exit_code == 0

    def test_wizard_cli_non_tty_prints_template(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["setup", "--wizard"], catch_exceptions=False)
        assert "SafeCode Setup Template" in result.output

    def test_wizard_cli_non_tty_does_not_write_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["setup", "--wizard"], catch_exceptions=False)
        assert not (tmp_path / ".sac" / "config.toml").exists()

    def test_wizard_flag_appears_in_help(self) -> None:
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        assert "--wizard" in result.output


# ---------------------------------------------------------------------------
# v3.7.1 wizard TTY safety tests
# ---------------------------------------------------------------------------

class TestWizardSafety:
    def test_wizard_preserves_stricter_policy(self, tmp_path: Path) -> None:
        """If current policy is strict, wizard cannot write a less-restrictive policy."""
        from safecode.config import SafeCodeConfig

        strict_config = SafeCodeConfig()
        strict_config.policy = "strict"

        written_policy = None

        def capture(*args, **kw):  # type: ignore[no-untyped-def]
            nonlocal written_policy
            written_policy = kw.get("policy")
            raise FileExistsError("stop")

        with (
            patch("safecode.cli.SafeCodeConfig.load", return_value=strict_config),
            patch("safecode.cli.typer.prompt") as mock_prompt,
            patch("safecode.cli.typer.confirm") as mock_confirm,
            patch("safecode.cli.write_setup", side_effect=capture),
        ):
            # Inputs: provider=mock, model=gpt-4.1-mini, policy=experimental
            # Confirms: network=no, write=yes
            mock_prompt.side_effect = ["mock", "gpt-4.1-mini", "experimental"]
            mock_confirm.side_effect = [False, True]
            run_setup_wizard(tmp_path, is_tty=True)

        # Policy must not be weaker than strict
        if written_policy is not None:
            from safecode.config import POLICY_ORDER
            assert POLICY_ORDER.get(written_policy, 0) >= POLICY_ORDER.get("strict", 2)

    def test_wizard_network_requires_double_confirm(self, tmp_path: Path) -> None:
        """Network stays off when second confirm is declined."""
        from safecode.config import SafeCodeConfig

        mock_config = SafeCodeConfig()
        mock_config.policy = "balanced"

        written_network = None

        def capture(*args, **kw):  # type: ignore[no-untyped-def]
            nonlocal written_network
            written_network = kw.get("network_enabled")
            raise FileExistsError("stop")

        with (
            patch("safecode.cli.SafeCodeConfig.load", return_value=mock_config),
            patch("safecode.cli.typer.prompt") as mock_prompt,
            patch("safecode.cli.typer.confirm") as mock_confirm,
            patch("safecode.cli.write_setup", side_effect=capture),
        ):
            mock_prompt.side_effect = ["mock", "gpt-4.1-mini", "balanced"]
            # First "enable network?" → True, second "are you sure?" → False, write → True
            mock_confirm.side_effect = [True, False, True]
            run_setup_wizard(tmp_path, is_tty=True)

        if written_network is not None:
            assert written_network is False

    def test_wizard_unknown_provider_falls_back_to_mock(self, tmp_path: Path) -> None:
        from safecode.config import SafeCodeConfig

        mock_config = SafeCodeConfig()
        mock_config.policy = "balanced"

        written_provider = None

        def capture(*args, **kw):  # type: ignore[no-untyped-def]
            nonlocal written_provider
            written_provider = kw.get("provider")
            raise FileExistsError("stop")

        with (
            patch("safecode.cli.SafeCodeConfig.load", return_value=mock_config),
            patch("safecode.cli.typer.prompt") as mock_prompt,
            patch("safecode.cli.typer.confirm") as mock_confirm,
            patch("safecode.cli.write_setup", side_effect=capture),
        ):
            mock_prompt.side_effect = ["notarealvendor", "gpt-4.1-mini", "balanced"]
            mock_confirm.side_effect = [False, True]
            run_setup_wizard(tmp_path, is_tty=True)

        assert written_provider in {"mock", None}

    def test_wizard_unknown_policy_falls_back_to_balanced(self, tmp_path: Path) -> None:
        from safecode.config import SafeCodeConfig

        mock_config = SafeCodeConfig()
        mock_config.policy = "balanced"

        written_policy = None

        def capture(*args, **kw):  # type: ignore[no-untyped-def]
            nonlocal written_policy
            written_policy = kw.get("policy")
            raise FileExistsError("stop")

        with (
            patch("safecode.cli.SafeCodeConfig.load", return_value=mock_config),
            patch("safecode.cli.typer.prompt") as mock_prompt,
            patch("safecode.cli.typer.confirm") as mock_confirm,
            patch("safecode.cli.write_setup", side_effect=capture),
        ):
            mock_prompt.side_effect = ["mock", "gpt-4.1-mini", "notapolicy"]
            mock_confirm.side_effect = [False, True]
            run_setup_wizard(tmp_path, is_tty=True)

        assert written_policy in {"balanced", None}

    def test_wizard_cancelled_does_not_write(self, tmp_path: Path) -> None:
        from safecode.config import SafeCodeConfig

        mock_config = SafeCodeConfig()
        mock_config.policy = "balanced"

        with (
            patch("safecode.cli.SafeCodeConfig.load", return_value=mock_config),
            patch("safecode.cli.typer.prompt") as mock_prompt,
            patch("safecode.cli.typer.confirm") as mock_confirm,
            patch("safecode.cli.write_setup") as mock_write,
        ):
            mock_prompt.side_effect = ["mock", "gpt-4.1-mini", "balanced"]
            mock_confirm.side_effect = [False, False]  # network=no, write=no
            code = run_setup_wizard(tmp_path, is_tty=True)

        assert code == 0
        mock_write.assert_not_called()
