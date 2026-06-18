"""Tests for v4.15.2 keychain and env-only credential storage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app

runner = CliRunner()


class TestProviderAddRequiresStore:
    def test_api_key_without_store_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        user_config = tmp_path / "user_config.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n'
            'base_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            app, ["provider", "add", "deepseek", "--api-key", "sk-test"],
            catch_exceptions=False,
        )
        assert result.exit_code == 1
        assert "--store" in result.stdout

    def test_api_key_with_store_user_config_works(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        user_config = tmp_path / "user_config.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n'
            'base_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            ["provider", "add", "deepseek", "--api-key", "sk-test",
             "--store", "user-config"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Provider 'deepseek' configured" in result.stdout

    def test_provider_add_bad_store_value_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app,
            ["provider", "add", "deepseek", "--api-key", "sk-test",
             "--store", "bad-value"],
            catch_exceptions=False,
        )
        assert result.exit_code == 1

    def test_api_key_with_store_keychain_does_not_write_key_to_user_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        user_config = tmp_path / "user_config.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n'
            'base_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )

        with patch("safecode.security.keychain.store_api_key", return_value=True) as store:
            result = runner.invoke(
                app,
                ["provider", "add", "deepseek", "--api-key", "sk-keychain-only",
                 "--store", "keychain"],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        store.assert_called_once_with("deepseek", "sk-keychain-only")
        assert "stored in system keychain" in result.stdout
        content = user_config.read_text(encoding="utf-8")
        assert "sk-keychain-only" not in content
        assert "api_key" not in content


class TestProviderAddNoApiKey:
    def test_provider_add_without_api_key_works(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Adding a provider without --api-key should succeed (env var path)."""
        monkeypatch.chdir(tmp_path)
        user_config = tmp_path / "user_config.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n'
            'base_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = true\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            app, ["provider", "add", "deepseek"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_provider_add_with_env_var_works(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-key")
        monkeypatch.chdir(tmp_path)
        user_config = tmp_path / "user_config.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n'
            'base_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = true\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            app, ["provider", "add", "deepseek"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Using DEEPSEEK_API_KEY from environment" in result.stdout


class TestKeychainBackend:
    def test_keychain_store_api_key(self) -> None:
        from safecode.security.keychain import store_api_key, get_api_key, delete_api_key
        with patch("safecode.security.keychain._get_keyring") as mock_kr:
            mock_backend = mock_kr.return_value
            mock_backend.set_password.return_value = None
            mock_backend.get_password.return_value = "sk-test"
            mock_backend.delete_password.return_value = None

            assert store_api_key("deepseek", "sk-test") is True
            assert get_api_key("deepseek") == "sk-test"
            assert delete_api_key("deepseek") is True

    def test_keychain_unavailable_graceful(self) -> None:
        from safecode.security.keychain import store_api_key, get_api_key, has_keychain_backend
        with patch("safecode.security.keychain._get_keyring", return_value=None):
            assert has_keychain_backend() is False
            assert store_api_key("deepseek", "sk-test") is False
            assert get_api_key("deepseek") is None


class TestKeychainEdgeCases:
    def test_get_after_set_raises_is_handled(self) -> None:
        """get_api_key returns None without crashing when get_password raises after a successful store.

        Covers the scenario where keyring is available but get_password raises
        an unexpected exception (e.g., backend corruption, platform error).
        """
        from safecode.security.keychain import get_api_key, store_api_key

        mock_backend = MagicMock()
        mock_backend.set_password.return_value = None  # store succeeds
        mock_backend.get_password.side_effect = RuntimeError("backend unavailable")

        with patch("safecode.security.keychain._get_keyring", return_value=mock_backend):
            stored = store_api_key("deepseek", "sk-test")
            assert stored is True  # store succeeded

            retrieved = get_api_key("deepseek")
            # Must not raise; returns None on error
            assert retrieved is None


class TestCredentialStorageDoctor:
    def test_doctor_reports_credential_storage(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "no-user-config.toml"))
        (tmp_path / ".sac").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".sac" / "config.toml").write_text(
            '[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n'
            'base_url = "http://localhost:8080/v1"\n'
            "[sandbox]\nnetwork_enabled = false\n",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["doctor"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "credential_storage" in result.stdout
