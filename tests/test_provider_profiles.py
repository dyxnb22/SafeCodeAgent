"""Tests for v4.14.0 provider profile store and CLI."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from safecode.cli import app
from safecode.llm.provider_profiles import (
    ProviderProfile,
    get_active_profile,
    get_active_profile_name,
    load_profiles,
    make_deepseek_profile,
    remove_profile,
    save_profile,
    set_active_provider,
    resolve_model_in_active_profile,
    _DEEPSEEK_ALIASES,
    _render_user_toml,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# ProviderProfile model
# ---------------------------------------------------------------------------


class TestProviderProfileModel:
    def test_default_fields(self) -> None:
        p = ProviderProfile(name="test")
        assert p.name == "test"
        assert p.base_url == ""
        assert p.api_key is None
        assert p.default_model == ""
        assert p.model_aliases == {}
        assert p.network_allowlist == []

    def test_resolve_empty_returns_default_model(self) -> None:
        p = ProviderProfile(name="deepseek", default_model="deepseek-v4-flash")
        resolved, hint = p.resolve_model("")
        assert resolved == "deepseek-v4-flash"
        assert hint is None

    def test_resolve_known_alias_flash(self) -> None:
        p = make_deepseek_profile()
        resolved, hint = p.resolve_model("flash")
        assert resolved == "deepseek-v4-flash"
        assert hint is None

    def test_resolve_known_alias_pro(self) -> None:
        p = make_deepseek_profile()
        resolved, hint = p.resolve_model("pro")
        assert resolved == "deepseek-v4-pro"
        assert hint is None

    def test_resolve_scoped_deepseek_flash(self) -> None:
        p = make_deepseek_profile()
        resolved, hint = p.resolve_model("deepseek:flash")
        assert resolved == "deepseek-v4-flash"

    def test_resolve_scoped_deepseek_pro(self) -> None:
        p = make_deepseek_profile()
        resolved, hint = p.resolve_model("deepseek:pro")
        assert resolved == "deepseek-v4-pro"

    def test_resolve_full_model_id_passthrough(self) -> None:
        p = make_deepseek_profile()
        resolved, hint = p.resolve_model("deepseek-v4-flash")
        assert resolved == "deepseek-v4-flash"
        assert hint is None

    def test_resolve_typo_suggests_correction(self) -> None:
        p = make_deepseek_profile()
        resolved, hint = p.resolve_model("deepseek-v4-falsh")
        assert resolved == "deepseek-v4-flash"
        assert hint is not None

    def test_api_key_source_env(self, monkeypatch) -> None:
        p = make_deepseek_profile()
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        assert p.api_key_source() == "env:DEEPSEEK_API_KEY"

    def test_api_key_source_user_config(self, monkeypatch) -> None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        p = make_deepseek_profile(api_key="sk-stored")
        assert p.api_key_source() == "user-config"

    def test_api_key_source_missing(self, monkeypatch) -> None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        p = make_deepseek_profile(api_key=None)
        assert p.api_key_source() == "missing"

    def test_effective_api_key_env_overrides_stored(self, monkeypatch) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
        p = make_deepseek_profile(api_key="sk-stored")
        assert p.effective_api_key() == "sk-from-env"

    def test_effective_api_key_falls_back_to_stored(self, monkeypatch) -> None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        p = make_deepseek_profile(api_key="sk-stored")
        assert p.effective_api_key() == "sk-stored"

    def test_effective_api_key_none_when_missing(self, monkeypatch) -> None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        p = make_deepseek_profile(api_key=None)
        assert p.effective_api_key() is None


# ---------------------------------------------------------------------------
# DeepSeek preset
# ---------------------------------------------------------------------------


class TestDeepSeekPreset:
    def test_make_deepseek_profile_base_url(self) -> None:
        p = make_deepseek_profile()
        assert p.base_url == "https://api.deepseek.com"

    def test_make_deepseek_profile_default_model(self) -> None:
        p = make_deepseek_profile()
        assert p.default_model == "deepseek-v4-flash"

    def test_make_deepseek_profile_aliases_complete(self) -> None:
        p = make_deepseek_profile()
        assert p.model_aliases["flash"] == "deepseek-v4-flash"
        assert p.model_aliases["pro"] == "deepseek-v4-pro"

    def test_make_deepseek_profile_network_allowlist(self) -> None:
        p = make_deepseek_profile()
        assert "api.deepseek.com" in p.network_allowlist

    def test_make_deepseek_profile_with_api_key(self) -> None:
        p = make_deepseek_profile(api_key="sk-test")
        assert p.api_key == "sk-test"

    def test_make_deepseek_profile_api_key_none(self) -> None:
        p = make_deepseek_profile()
        assert p.api_key is None


# ---------------------------------------------------------------------------
# Profile store persistence
# ---------------------------------------------------------------------------


class TestProfileStorePersistence:
    def test_save_and_load_profile(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        p = make_deepseek_profile(api_key="sk-test")
        save_profile(p, cfg)

        profiles = load_profiles(cfg)
        assert "deepseek" in profiles
        loaded = profiles["deepseek"]
        assert loaded.base_url == "https://api.deepseek.com"
        assert loaded.default_model == "deepseek-v4-flash"
        assert "flash" in loaded.model_aliases
        assert loaded.api_key == "sk-test"

    def test_save_redacted_from_output_not_from_storage(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        p = make_deepseek_profile(api_key="sk-super-secret")
        save_profile(p, cfg)
        # Stored in user config (trusted) - readable in raw TOML
        content = cfg.read_text()
        assert "sk-super-secret" in content
        # But api_key_source() never returns the raw key
        profiles = load_profiles(cfg)
        source = profiles["deepseek"].api_key_source()
        assert "sk-super-secret" not in source
        assert source == "user-config"

    def test_save_sets_active(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        p = make_deepseek_profile()
        save_profile(p, cfg)
        set_active_provider("deepseek", cfg)
        assert get_active_profile_name(cfg) == "deepseek"

    def test_get_active_profile_returns_none_when_none_set(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        assert get_active_profile(cfg) is None

    def test_remove_profile(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        p = make_deepseek_profile()
        save_profile(p, cfg)
        set_active_provider("deepseek", cfg)
        removed = remove_profile("deepseek", cfg)
        assert removed is True
        profiles = load_profiles(cfg)
        assert "deepseek" not in profiles
        # Active is also cleared
        assert get_active_profile_name(cfg) is None

    def test_remove_nonexistent_profile(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        removed = remove_profile("nonexistent", cfg)
        assert removed is False

    def test_load_empty_config_returns_empty(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        profiles = load_profiles(cfg)
        assert profiles == {}

    def test_save_preserves_existing_llm_section(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text('[llm]\nprovider = "mock"\nmodel = "gpt-4.1-mini"\n', encoding="utf-8")
        p = make_deepseek_profile()
        save_profile(p, cfg)
        content = cfg.read_text()
        assert 'provider = "mock"' in content
        assert "deepseek" in content

    def test_api_key_not_written_to_project_config(self, tmp_path: Path) -> None:
        project_cfg = tmp_path / ".sac" / "config.toml"
        project_cfg.parent.mkdir()
        project_cfg.write_text("", encoding="utf-8")
        # save_profile goes to user config, not project config
        user_cfg = tmp_path / "user.toml"
        p = make_deepseek_profile(api_key="sk-secret")
        save_profile(p, user_cfg)
        project_content = project_cfg.read_text()
        assert "sk-secret" not in project_content


# ---------------------------------------------------------------------------
# Alias resolution helper
# ---------------------------------------------------------------------------


class TestResolveModelInActiveProfile:
    def test_resolves_flash_when_deepseek_active(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        p = make_deepseek_profile()
        save_profile(p, cfg)
        set_active_provider("deepseek", cfg)
        resolved = resolve_model_in_active_profile("flash", cfg)
        assert resolved == "deepseek-v4-flash"

    def test_resolves_pro(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        p = make_deepseek_profile()
        save_profile(p, cfg)
        set_active_provider("deepseek", cfg)
        resolved = resolve_model_in_active_profile("pro", cfg)
        assert resolved == "deepseek-v4-pro"

    def test_resolves_deepseek_scoped(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        p = make_deepseek_profile()
        save_profile(p, cfg)
        set_active_provider("deepseek", cfg)
        resolved = resolve_model_in_active_profile("deepseek:flash", cfg)
        assert resolved == "deepseek-v4-flash"

    def test_returns_none_when_no_active_profile(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        resolved = resolve_model_in_active_profile("flash", cfg)
        assert resolved is None


# ---------------------------------------------------------------------------
# TOML renderer roundtrip
# ---------------------------------------------------------------------------


class TestRenderUserToml:
    def test_renders_providers_section(self) -> None:
        data = {
            "providers": {
                "active": "deepseek",
                "deepseek": {"base_url": "https://api.deepseek.com", "default_model": "deepseek-v4-flash"},
            }
        }
        text = _render_user_toml(data)
        assert "[providers]" in text
        assert 'active = "deepseek"' in text
        assert "[providers.deepseek]" in text
        assert "deepseek.com" in text

    def test_roundtrip_via_tomllib(self) -> None:
        import tomllib
        data = {
            "providers": {
                "active": "deepseek",
                "deepseek": {
                    "base_url": "https://api.deepseek.com",
                    "default_model": "deepseek-v4-flash",
                    "model_aliases": {"flash": "deepseek-v4-flash", "pro": "deepseek-v4-pro"},
                    "network_allowlist": ["api.deepseek.com"],
                },
            }
        }
        text = _render_user_toml(data)
        parsed = tomllib.loads(text)
        assert parsed["providers"]["active"] == "deepseek"
        assert parsed["providers"]["deepseek"]["base_url"] == "https://api.deepseek.com"

    def test_llm_section_preserved(self) -> None:
        data = {
            "llm": {"provider": "mock", "model": "gpt-4.1-mini"},
            "providers": {"active": "deepseek"},
        }
        text = _render_user_toml(data)
        assert "[llm]" in text
        assert 'provider = "mock"' in text
        assert "[providers]" in text


# ---------------------------------------------------------------------------
# sac provider CLI commands
# ---------------------------------------------------------------------------


class TestProviderAddCLI:
    def test_provider_add_deepseek_non_tty(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-test", "--yes"])
        assert result.exit_code == 0, result.output
        assert "deepseek" in result.output.lower()

        profiles = load_profiles(user_config)
        assert "deepseek" in profiles
        p = profiles["deepseek"]
        assert p.base_url == "https://api.deepseek.com"
        assert p.api_key == "sk-test"
        assert p.model_aliases["flash"] == "deepseek-v4-flash"
        assert p.model_aliases["pro"] == "deepseek-v4-pro"
        assert "api.deepseek.com" in p.network_allowlist

    def test_provider_add_sets_active(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-test", "--yes"])
        active = get_active_profile_name(user_config)
        assert active == "deepseek"

    def test_provider_add_writes_network_allowlist(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-test", "--yes"])
        import tomllib
        data = tomllib.loads(user_config.read_text())
        allowlist = data.get("sandbox", {}).get("network_allowlist", [])
        assert "api.deepseek.com" in allowlist
        assert data.get("sandbox", {}).get("network_enabled") is True

    def test_provider_add_unknown_provider_fails(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["provider", "add", "nonexistent", "--yes"])
        assert result.exit_code != 0

    def test_provider_add_api_key_not_in_project_config(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        sac_dir = project_dir / ".sac"
        sac_dir.mkdir()
        (sac_dir / "config.toml").write_text("", encoding="utf-8")

        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(project_dir)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-secret", "--yes"])

        project_content = (sac_dir / "config.toml").read_text()
        assert "sk-secret" not in project_content

    def test_provider_add_default_model_override(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--default-model", "pro", "--yes"])
        profiles = load_profiles(user_config)
        assert profiles["deepseek"].default_model == "deepseek-v4-pro"

    def test_provider_add_shows_next_step_hint(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        assert "model" in result.output.lower()

    def test_provider_add_env_var_not_persisted(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["provider", "add", "deepseek", "--yes"])
        assert result.exit_code == 0
        # api_key should NOT be persisted when only env var provides it
        profiles = load_profiles(user_config)
        assert profiles["deepseek"].api_key is None


class TestProviderListCLI:
    def test_provider_list_empty(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["provider", "list"])
        assert result.exit_code == 0
        assert "No provider profiles" in result.output or "provider add" in result.output.lower()

    def test_provider_list_shows_active(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["provider", "list"])
        assert result.exit_code == 0
        assert "deepseek" in result.output
        assert "active" in result.output


class TestProviderStatusCLI:
    def test_provider_status_no_profile(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["provider", "status"])
        assert result.exit_code == 0
        assert "provider" in result.output.lower()

    def test_provider_status_shows_effective_provider(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["provider", "status"])
        assert result.exit_code == 0
        assert "deepseek" in result.output

    def test_provider_status_never_shows_raw_api_key(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-super-secret", "--yes"])
        result = runner.invoke(app, ["provider", "status"])
        assert "sk-super-secret" not in result.output


class TestProviderUseCLI:
    def test_provider_use_sets_active(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["provider", "use", "deepseek"])
        assert result.exit_code == 0
        assert get_active_profile_name(user_config) == "deepseek"

    def test_provider_use_missing_provider_fails(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["provider", "use", "nonexistent"])
        assert result.exit_code != 0


class TestProviderRmCLI:
    def test_provider_rm_removes_profile(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["provider", "rm", "deepseek", "--yes"])
        assert result.exit_code == 0
        assert "deepseek" not in load_profiles(user_config)

    def test_provider_rm_nonexistent_graceful(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["provider", "rm", "nonexistent", "--yes"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# sac model alias resolution
# ---------------------------------------------------------------------------


class TestModelAliasResolution:
    def test_model_flash_resolves_via_profile(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["model", "flash"])
        assert result.exit_code == 0, result.output
        assert "deepseek-v4-flash" in result.output

    def test_model_pro_resolves_via_profile(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["model", "pro"])
        assert result.exit_code == 0, result.output
        assert "deepseek-v4-pro" in result.output

    def test_model_deepseek_scoped_resolves(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["model", "deepseek:pro"])
        assert result.exit_code == 0, result.output
        assert "deepseek-v4-pro" in result.output

    def test_model_wrong_scoped_provider_fails_with_guidance(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["model", "openai:gpt-4o"])
        assert result.exit_code != 0
        assert "active provider" in result.output

    def test_model_list_shows_aliases(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["model", "list"])
        assert result.exit_code == 0
        assert "flash" in result.output
        assert "pro" in result.output

    def test_model_list_no_profile_guidance(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["model", "list"])
        assert result.exit_code == 0
        assert "provider add" in result.output.lower() or "No active" in result.output

    def test_model_alias_persists_to_user_config(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        runner.invoke(app, ["model", "flash"])
        import tomllib
        data = tomllib.loads(user_config.read_text())
        assert data["llm"]["model"] == "deepseek-v4-flash"
        assert data["providers"]["deepseek"]["default_model"] == "deepseek-v4-flash"

    def test_model_raw_id_updates_active_profile_default(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["model", "deepseek-v4-pro"])
        assert result.exit_code == 0, result.output
        import tomllib
        data = tomllib.loads(user_config.read_text())
        assert data["providers"]["deepseek"]["default_model"] == "deepseek-v4-pro"


# ---------------------------------------------------------------------------
# Runtime resolution: env vars override profile
# ---------------------------------------------------------------------------


class TestEnvVarOverrideProfile:
    def test_safecode_llm_provider_overrides_active_profile(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.setenv("SAFECODE_LLM_PROVIDER", "openai")
        monkeypatch.chdir(tmp_path)

        p = make_deepseek_profile()
        save_profile(p, user_config)
        set_active_provider("deepseek", user_config)

        from safecode.config import SafeCodeConfig
        config = SafeCodeConfig.load(tmp_path)
        assert config.llm.provider == "openai"

    def test_safecode_llm_model_overrides_profile_default(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.setenv("SAFECODE_LLM_MODEL", "gpt-4o")
        monkeypatch.chdir(tmp_path)

        p = make_deepseek_profile()
        save_profile(p, user_config)
        set_active_provider("deepseek", user_config)

        from safecode.config import SafeCodeConfig
        config = SafeCodeConfig.load(tmp_path)
        assert config.llm.model == "gpt-4o"

    def test_active_profile_overrides_legacy_llm_section(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        # Write explicit [llm] section and a deepseek profile
        p = make_deepseek_profile()
        save_profile(p, user_config)
        set_active_provider("deepseek", user_config)

        import tomllib
        from safecode.llm.provider_profiles import _render_user_toml
        data = tomllib.loads(user_config.read_text())
        data["llm"] = {"provider": "mock", "model": "test-model"}
        user_config.write_text(_render_user_toml(data))

        from safecode.config import SafeCodeConfig
        config = SafeCodeConfig.load(tmp_path)
        # Active provider profile wins over legacy [llm]; env vars still win.
        assert config.llm.provider == "deepseek"
        assert config.llm.model == "deepseek-v4-flash"

    def test_active_profile_fills_provider_when_llm_not_set(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.delenv("SAFECODE_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("SAFECODE_LLM_MODEL", raising=False)
        monkeypatch.chdir(tmp_path)

        p = make_deepseek_profile()
        save_profile(p, user_config)
        set_active_provider("deepseek", user_config)

        from safecode.config import SafeCodeConfig
        config = SafeCodeConfig.load(tmp_path)
        assert config.llm.provider == "deepseek"
        assert config.llm.model == "deepseek-v4-flash"
        assert config.llm.base_url == "https://api.deepseek.com"


# ---------------------------------------------------------------------------
# Project config cannot widen credentials or network
# ---------------------------------------------------------------------------


class TestProjectConfigSafety:
    def test_project_config_cannot_set_api_key_via_providers(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        sac_dir = project_dir / ".sac"
        sac_dir.mkdir()
        # Try to inject a credential via project config providers section
        (sac_dir / "config.toml").write_text(
            '[providers.deepseek]\napi_key = "sk-injected"\n', encoding="utf-8"
        )
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(project_dir)

        from safecode.config import SafeCodeConfig
        config = SafeCodeConfig.load(project_dir)
        # Project config providers section is NOT loaded - only user config is
        assert config.llm.api_key != "sk-injected"

    def test_project_config_cannot_widen_network_via_providers(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        sac_dir = project_dir / ".sac"
        sac_dir.mkdir()
        (sac_dir / "config.toml").write_text(
            '[sandbox]\nnetwork_enabled = true\n', encoding="utf-8"
        )
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(project_dir)

        from safecode.config import SafeCodeConfig
        config = SafeCodeConfig.load(project_dir)
        # Project cannot enable network without user-level opt-in
        assert config.sandbox.network_enabled is False


# ---------------------------------------------------------------------------
# Shell /model and /provider status
# ---------------------------------------------------------------------------


class TestShellModelAlias:
    def test_shell_model_shows_status(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["shell", "--non-tty"], input="/model\n/exit\n")
        assert result.exit_code == 0
        assert "Model" in result.output or "Provider" in result.output

    def test_shell_model_pro_resolves_and_persists(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["shell", "--non-tty"], input="/model pro\n/exit\n")
        assert result.exit_code == 0
        assert "deepseek-v4-pro" in result.output

    def test_shell_model_says_saved_globally(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["shell", "--non-tty"], input="/model flash\n/exit\n")
        # Output should say something about persisted/saved
        assert "saved" in result.output.lower() or "globally" in result.output.lower()


class TestShellProviderStatus:
    def test_slash_provider_status_shows_provider(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["shell", "--non-tty"], input="/provider status\n/exit\n")
        assert result.exit_code == 0
        assert "deepseek" in result.output.lower()

    def test_slash_provider_status_no_raw_key(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-very-secret", "--yes"])
        result = runner.invoke(app, ["shell", "--non-tty"], input="/provider status\n/exit\n")
        assert "sk-very-secret" not in result.output

    def test_slash_provider_status_no_profile_shows_guidance(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["shell", "--non-tty"], input="/provider status\n/exit\n")
        assert result.exit_code == 0


class TestOneShotModelOverride:
    def test_root_model_override_affects_subcommand_without_persisting(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(app, ["--model", "deepseek:pro", "provider", "status"])
        assert result.exit_code == 0, result.output
        assert "Effective model         : deepseek-v4-pro" in result.output

        profiles = load_profiles(user_config)
        assert profiles["deepseek"].default_model == "deepseek-v4-flash"

    def test_shell_model_option_affects_session_status(self, tmp_path: Path, monkeypatch) -> None:
        user_config = tmp_path / "user.toml"
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(user_config))
        monkeypatch.chdir(tmp_path)

        runner.invoke(app, ["provider", "add", "deepseek", "--api-key", "sk-x", "--yes"])
        result = runner.invoke(
            app,
            ["shell", "--model", "pro", "--non-tty"],
            input="/provider status\n/exit\n",
        )
        assert result.exit_code == 0, result.output
        assert "Effective model         : deepseek-v4-pro" in result.output

    def test_shell_help_mentions_model_option(self) -> None:
        result = runner.invoke(app, ["shell", "--help"])
        assert result.exit_code == 0
        assert "--model" in result.output


# ---------------------------------------------------------------------------
# Provider in sac --help
# ---------------------------------------------------------------------------


class TestProviderInHelp:
    def test_provider_group_visible_in_help(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "provider" in result.output

    def test_provider_add_in_help(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["provider", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
