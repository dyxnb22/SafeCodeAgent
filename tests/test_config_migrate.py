"""Tests for v4.16.1 config migration."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from safecode.cli import app

runner = CliRunner()


class TestConfigMigrate:
    def test_migrate_no_config_shows_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "nonexistent.toml"))
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app, ["config", "migrate", "--yes"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "No user config found" in result.stdout

    def test_migrate_with_legacy_llm_creates_backup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_config = tmp_path / "user.toml"
        user_config.write_text(
            '[llm]\nprovider = "deepseek"\nmodel = "deepseek-v4-flash"\n'
            'base_url = "https://api.deepseek.com"\n'
            'api_key = "sk-legacy-test"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app, ["config", "migrate", "--yes"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Backup saved" in result.stdout
        assert "Migrated legacy" in result.stdout

        # Backup exists
        backup = Path(str(user_config) + ".bak")
        assert backup.exists()

        # User config now has providers section
        content = user_config.read_text()
        assert "[providers]" in content
        assert "[providers.deepseek]" in content or "providers.deepseek" in content
        assert "sk-legacy-test" in content

    def test_migrate_mock_provider_skips(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_config = tmp_path / "user.toml"
        user_config.write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app, ["config", "migrate", "--yes"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Nothing to migrate" in result.stdout


class TestLegacyLLMDoctor:
    def test_doctor_warns_on_legacy_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_config = tmp_path / "user.toml"
        user_config.write_text(
            '[llm]\nprovider = "deepseek"\nmodel = "deepseek-v4-flash"\n'
            'base_url = "https://api.deepseek.com"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "deepseek"\nmodel = "deepseek-v4-flash"\n'
            'base_url = "https://api.deepseek.com/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["doctor"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "legacy_llm_section" in result.stdout
