"""Tests for v2.6.1 migration hardening: unknown policy names, env-var safety, setup surface."""

import warnings
from pathlib import Path

import pytest

from safecode.config import (
    KNOWN_POLICY_NAMES,
    SafeCodeConfig,
    is_known_policy_name,
    merge_trusted_config,
    normalize_policy_name,
)
from safecode.setup import write_setup


# ---------------------------------------------------------------------------
# is_known_policy_name
# ---------------------------------------------------------------------------


class TestIsKnownPolicyName:
    def test_canonical_names_known(self):
        for name in ("strict", "balanced", "experimental"):
            assert is_known_policy_name(name) is True

    def test_legacy_aliases_known(self):
        assert is_known_policy_name("normal") is True
        assert is_known_policy_name("learning") is True

    def test_unknown_names_not_known(self):
        for name in ("reckless", "custom", "super-strict", "", "STRICT"):
            assert is_known_policy_name(name) is False

    def test_known_policy_names_frozenset_contains_all_five(self):
        assert {"strict", "balanced", "experimental", "normal", "learning"} <= KNOWN_POLICY_NAMES

    def test_empty_string_not_known(self):
        assert is_known_policy_name("") is False

    def test_case_sensitive(self):
        assert is_known_policy_name("Strict") is False
        assert is_known_policy_name("BALANCED") is False


# ---------------------------------------------------------------------------
# _stricter_policy via merge_trusted_config – unknown right side
# ---------------------------------------------------------------------------


class TestStricterPolicyUnknownRight:
    """Project config with unknown policy name must not override user config."""

    def _config(self, policy: str) -> SafeCodeConfig:
        return SafeCodeConfig(policy=policy)

    def test_unknown_project_does_not_override_strict_user(self):
        merged = merge_trusted_config(self._config("strict"), self._config("future_policy"))
        assert merged.policy == "strict"

    def test_unknown_project_does_not_override_balanced_user(self):
        merged = merge_trusted_config(self._config("balanced"), self._config("unknown_policy"))
        assert merged.policy == "balanced"

    def test_unknown_project_does_not_override_experimental_user(self):
        # Before hardening: unknown right would win (default order=1 > 0).
        # After hardening: unknown right never overrides known left.
        merged = merge_trusted_config(self._config("experimental"), self._config("unknown_policy"))
        assert merged.policy == "experimental"

    def test_unknown_project_does_not_override_normal_alias(self):
        merged = merge_trusted_config(self._config("normal"), self._config("unknown_policy"))
        assert merged.policy == "normal"

    def test_unknown_project_does_not_override_learning_alias(self):
        merged = merge_trusted_config(self._config("learning"), self._config("unknown_policy"))
        assert merged.policy == "learning"

    def test_both_unknown_keeps_left(self):
        merged = merge_trusted_config(self._config("unknown_a"), self._config("unknown_b"))
        assert merged.policy == "unknown_a"


# ---------------------------------------------------------------------------
# _stricter_policy via merge_trusted_config – unknown left side
# ---------------------------------------------------------------------------


class TestStricterPolicyUnknownLeft:
    """Unknown user policy compared conservatively (as balanced=1)."""

    def _config(self, policy: str) -> SafeCodeConfig:
        return SafeCodeConfig(policy=policy)

    def test_unknown_user_yields_to_stricter_project(self):
        # unknown left treated as balanced=1; strict=2 is stricter → strict wins
        merged = merge_trusted_config(self._config("unknown_policy"), self._config("strict"))
        assert merged.policy == "strict"

    def test_unknown_user_keeps_left_against_balanced(self):
        # unknown left treated as balanced=1; balanced=1 is equal → left wins
        merged = merge_trusted_config(self._config("unknown_policy"), self._config("balanced"))
        assert merged.policy == "unknown_policy"

    def test_unknown_user_keeps_left_against_experimental(self):
        # unknown left treated as balanced=1; experimental=0 is looser → left wins
        merged = merge_trusted_config(self._config("unknown_policy"), self._config("experimental"))
        assert merged.policy == "unknown_policy"


# ---------------------------------------------------------------------------
# SAFECODE_POLICY env var: unknown values are warned and skipped
# ---------------------------------------------------------------------------


class TestSafecodePolicyEnvUnknown:
    def _setup_tmp(self, tmp_path: Path, monkeypatch, user_policy: str = "balanced") -> Path:
        """Write user config and a matching project config so merge doesn't interfere."""
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user.toml"))
        (tmp_path / "user.toml").write_text(f'policy = "{user_policy}"\n', encoding="utf-8")
        sac = tmp_path / ".sac"
        sac.mkdir()
        (sac / "config.toml").write_text(f'policy = "{user_policy}"\n', encoding="utf-8")
        return tmp_path

    def test_unknown_env_var_issues_user_warning(self, tmp_path, monkeypatch):
        self._setup_tmp(tmp_path, monkeypatch)
        monkeypatch.setenv("SAFECODE_POLICY", "super_secure_v9")
        with pytest.warns(UserWarning, match="super_secure_v9"):
            SafeCodeConfig.load(tmp_path)

    def test_unknown_env_var_does_not_change_policy(self, tmp_path, monkeypatch):
        self._setup_tmp(tmp_path, monkeypatch, user_policy="balanced")
        monkeypatch.setenv("SAFECODE_POLICY", "super_secure_v9")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "balanced"

    def test_unknown_env_var_cannot_override_strict(self, tmp_path, monkeypatch):
        self._setup_tmp(tmp_path, monkeypatch, user_policy="strict")
        monkeypatch.setenv("SAFECODE_POLICY", "unknown_policy")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "strict"

    def test_unknown_env_var_cannot_lower_experimental_to_unknown(self, tmp_path, monkeypatch):
        self._setup_tmp(tmp_path, monkeypatch, user_policy="experimental")
        monkeypatch.setenv("SAFECODE_POLICY", "reckless")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "experimental"

    def test_warning_message_includes_policy_name(self, tmp_path, monkeypatch):
        self._setup_tmp(tmp_path, monkeypatch)
        monkeypatch.setenv("SAFECODE_POLICY", "my_bad_policy")
        with pytest.warns(UserWarning, match="my_bad_policy"):
            SafeCodeConfig.load(tmp_path)

    def test_known_env_var_still_works_balanced(self, tmp_path, monkeypatch):
        self._setup_tmp(tmp_path, monkeypatch, user_policy="experimental")
        monkeypatch.setenv("SAFECODE_POLICY", "balanced")
        config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "balanced"

    def test_known_env_var_legacy_alias_still_works(self, tmp_path, monkeypatch):
        self._setup_tmp(tmp_path, monkeypatch, user_policy="experimental")
        monkeypatch.setenv("SAFECODE_POLICY", "normal")
        config = SafeCodeConfig.load(tmp_path)
        # "normal" (order=1) is stricter than "experimental" (order=0) → "normal" wins
        assert config.policy == "normal"

    def test_known_env_var_no_warning_issued(self, tmp_path, monkeypatch):
        self._setup_tmp(tmp_path, monkeypatch)
        monkeypatch.setenv("SAFECODE_POLICY", "strict")
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "strict"


# ---------------------------------------------------------------------------
# write_setup: new canonical names accepted, unknown names rejected
# ---------------------------------------------------------------------------


class TestWriteSetupPolicyNames:
    def _dirs(self, tmp_path: Path) -> dict:
        return {
            "approval_dir": tmp_path.parent / "approvals",
            "sandbox_approval_dir": tmp_path.parent / "sandbox-approvals",
        }

    def test_balanced_accepted(self, tmp_path):
        result = write_setup(tmp_path, policy="balanced", **self._dirs(tmp_path))
        assert result.policy == "balanced"
        assert 'policy = "balanced"' in result.config_path.read_text(encoding="utf-8")

    def test_default_policy_is_canonical_balanced(self, tmp_path):
        result = write_setup(tmp_path, **self._dirs(tmp_path))
        assert result.policy == "balanced"
        assert 'policy = "balanced"' in result.config_path.read_text(encoding="utf-8")

    def test_experimental_accepted(self, tmp_path):
        result = write_setup(tmp_path, policy="experimental", **self._dirs(tmp_path))
        assert result.policy == "experimental"
        assert 'policy = "experimental"' in result.config_path.read_text(encoding="utf-8")

    def test_strict_still_accepted(self, tmp_path):
        result = write_setup(tmp_path, policy="strict", **self._dirs(tmp_path))
        assert result.policy == "strict"

    def test_legacy_normal_still_accepted(self, tmp_path):
        result = write_setup(tmp_path, policy="normal", **self._dirs(tmp_path))
        assert result.policy == "normal"

    def test_legacy_learning_still_accepted(self, tmp_path):
        result = write_setup(tmp_path, policy="learning", **self._dirs(tmp_path))
        assert result.policy == "learning"

    def test_unknown_policy_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="policy"):
            write_setup(tmp_path, policy="reckless", **self._dirs(tmp_path))

    def test_empty_policy_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="policy"):
            write_setup(tmp_path, policy="", **self._dirs(tmp_path))

    def test_error_message_lists_known_names(self, tmp_path):
        with pytest.raises(ValueError) as exc_info:
            write_setup(tmp_path, policy="bad_policy", **self._dirs(tmp_path))
        msg = str(exc_info.value)
        assert "balanced" in msg or "strict" in msg


# ---------------------------------------------------------------------------
# End-to-end legacy alias migration: load + merge round-trip
# ---------------------------------------------------------------------------


class TestLegacyAliasMigrationRoundTrip:
    """Verify that configs using legacy names survive the full load+merge cycle safely."""

    def _write_config(self, path: Path, policy: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'policy = "{policy}"\n', encoding="utf-8")

    def test_normal_user_strict_project_merges_to_strict(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user.toml"))
        self._write_config(tmp_path / "user.toml", "normal")
        self._write_config(tmp_path / ".sac" / "config.toml", "strict")
        config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "strict"

    def test_learning_user_balanced_project_merges_to_balanced(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user.toml"))
        self._write_config(tmp_path / "user.toml", "learning")
        self._write_config(tmp_path / ".sac" / "config.toml", "balanced")
        config = SafeCodeConfig.load(tmp_path)
        # balanced (1) > learning/experimental (0) → balanced wins
        assert config.policy == "balanced"

    def test_normal_user_experimental_project_stays_normal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user.toml"))
        self._write_config(tmp_path / "user.toml", "normal")
        self._write_config(tmp_path / ".sac" / "config.toml", "experimental")
        config = SafeCodeConfig.load(tmp_path)
        # normal (1) >= experimental (0) → normal wins
        assert config.policy == "normal"

    def test_unknown_project_policy_does_not_override_user(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user.toml"))
        self._write_config(tmp_path / "user.toml", "balanced")
        self._write_config(tmp_path / ".sac" / "config.toml", "future_policy_v3")
        config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "balanced"

    def test_strict_user_unknown_project_stays_strict(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user.toml"))
        self._write_config(tmp_path / "user.toml", "strict")
        self._write_config(tmp_path / ".sac" / "config.toml", "experimental_v2")
        config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "strict"

    def test_safety_knobs_not_lowered_through_alias_migration(self, tmp_path, monkeypatch):
        """block_high_risk must stay True regardless of alias vs canonical name."""
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user.toml"))
        self._write_config(tmp_path / "user.toml", "normal")
        (tmp_path / ".sac").mkdir(exist_ok=True)
        config = SafeCodeConfig.load(tmp_path)
        assert config.shell.block_high_risk is True
        assert config.sandbox.restrict_to_project_root is True


# ---------------------------------------------------------------------------
# normalize_policy_name is stable (regression guard)
# ---------------------------------------------------------------------------


class TestNormalizePolicyStable:
    def test_all_known_names_normalize_to_known(self):
        for name in KNOWN_POLICY_NAMES:
            canonical = normalize_policy_name(name)
            assert is_known_policy_name(canonical), f"{name!r} → {canonical!r} is unknown"

    def test_unknown_names_pass_through_normalize(self):
        assert normalize_policy_name("future_v3") == "future_v3"
        assert normalize_policy_name("") == ""
