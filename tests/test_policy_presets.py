"""Tests for v2.6.0 policy presets: normalize_policy_name, apply_policy_preset, merge behavior."""

import os

import pytest

from safecode.config import (
    POLICY_ORDER,
    POLICY_PRESETS,
    SafeCodeConfig,
    apply_policy_preset,
    merge_trusted_config,
    normalize_policy_name,
)


# ---------------------------------------------------------------------------
# normalize_policy_name
# ---------------------------------------------------------------------------


class TestNormalizePolicyName:
    def test_normal_maps_to_balanced(self):
        assert normalize_policy_name("normal") == "balanced"

    def test_learning_maps_to_experimental(self):
        assert normalize_policy_name("learning") == "experimental"

    def test_strict_passthrough(self):
        assert normalize_policy_name("strict") == "strict"

    def test_balanced_passthrough(self):
        assert normalize_policy_name("balanced") == "balanced"

    def test_experimental_passthrough(self):
        assert normalize_policy_name("experimental") == "experimental"

    def test_unknown_passthrough(self):
        assert normalize_policy_name("custom") == "custom"


# ---------------------------------------------------------------------------
# POLICY_ORDER covers all five names
# ---------------------------------------------------------------------------


class TestPolicyOrder:
    def test_all_canonical_names_present(self):
        for name in ("strict", "balanced", "experimental"):
            assert name in POLICY_ORDER

    def test_aliases_present(self):
        assert "normal" in POLICY_ORDER
        assert "learning" in POLICY_ORDER

    def test_strict_highest(self):
        assert POLICY_ORDER["strict"] > POLICY_ORDER["balanced"]
        assert POLICY_ORDER["strict"] > POLICY_ORDER["experimental"]

    def test_balanced_above_experimental(self):
        assert POLICY_ORDER["balanced"] > POLICY_ORDER["experimental"]

    def test_aliases_equal_to_canonical(self):
        assert POLICY_ORDER["normal"] == POLICY_ORDER["balanced"]
        assert POLICY_ORDER["learning"] == POLICY_ORDER["experimental"]


# ---------------------------------------------------------------------------
# POLICY_PRESETS structure
# ---------------------------------------------------------------------------


class TestPolicyPresetsStructure:
    _REQUIRED_KEYS = {
        "allow_readonly_without_confirm",
        "require_confirm_for_medium",
        "block_high_risk",
        "allowed_commands",
        "restrict_to_project_root",
        "network_enabled",
        "network_allowlist",
        "allow_medium_after_apply",
    }

    def test_canonical_names_present(self):
        for name in ("strict", "balanced", "experimental"):
            assert name in POLICY_PRESETS

    @pytest.mark.parametrize("preset", ["strict", "balanced", "experimental"])
    def test_all_required_keys_present(self, preset):
        assert self._REQUIRED_KEYS <= set(POLICY_PRESETS[preset].keys())

    def test_block_high_risk_always_true(self):
        for preset in POLICY_PRESETS.values():
            assert preset["block_high_risk"] is True

    def test_restrict_to_project_root_always_true(self):
        for preset in POLICY_PRESETS.values():
            assert preset["restrict_to_project_root"] is True

    def test_network_disabled_in_all_presets(self):
        for preset in POLICY_PRESETS.values():
            assert preset["network_enabled"] is False

    def test_strict_allowed_commands_subset_of_balanced(self):
        strict_cmds = set(POLICY_PRESETS["strict"]["allowed_commands"])
        balanced_cmds = set(POLICY_PRESETS["balanced"]["allowed_commands"])
        assert strict_cmds <= balanced_cmds

    def test_balanced_allowed_commands_subset_of_experimental(self):
        balanced_cmds = set(POLICY_PRESETS["balanced"]["allowed_commands"])
        exp_cmds = set(POLICY_PRESETS["experimental"]["allowed_commands"])
        assert balanced_cmds <= exp_cmds


# ---------------------------------------------------------------------------
# apply_policy_preset – strict
# ---------------------------------------------------------------------------


class TestApplyPresetStrict:
    def _strict_config(self) -> SafeCodeConfig:
        config = SafeCodeConfig(policy="strict")
        apply_policy_preset(config)
        return config

    def test_allow_readonly_without_confirm_false(self):
        assert self._strict_config().shell.allow_readonly_without_confirm is False

    def test_require_confirm_for_medium_true(self):
        assert self._strict_config().shell.require_confirm_for_medium is True

    def test_block_high_risk_true(self):
        assert self._strict_config().shell.block_high_risk is True

    def test_network_disabled(self):
        assert self._strict_config().sandbox.network_enabled is False

    def test_restrict_to_project_root(self):
        assert self._strict_config().sandbox.restrict_to_project_root is True

    def test_allow_medium_after_apply_false(self):
        assert self._strict_config().hooks.allow_medium_after_apply is False

    def test_allowed_commands_matches_preset(self):
        assert set(self._strict_config().shell.allowed_commands) == set(POLICY_PRESETS["strict"]["allowed_commands"])

    def test_idempotent(self):
        config = SafeCodeConfig(policy="strict")
        apply_policy_preset(config)
        knobs_first = config.model_dump()
        apply_policy_preset(config)
        assert config.model_dump() == knobs_first


# ---------------------------------------------------------------------------
# apply_policy_preset – balanced
# ---------------------------------------------------------------------------


class TestApplyPresetBalanced:
    def _balanced_config(self) -> SafeCodeConfig:
        config = SafeCodeConfig(policy="balanced")
        apply_policy_preset(config)
        return config

    def test_allow_readonly_without_confirm_true(self):
        assert self._balanced_config().shell.allow_readonly_without_confirm is True

    def test_require_confirm_for_medium_true(self):
        assert self._balanced_config().shell.require_confirm_for_medium is True

    def test_block_high_risk_true(self):
        assert self._balanced_config().shell.block_high_risk is True

    def test_network_disabled(self):
        assert self._balanced_config().sandbox.network_enabled is False

    def test_allow_medium_after_apply_false(self):
        assert self._balanced_config().hooks.allow_medium_after_apply is False

    def test_allowed_commands_matches_preset(self):
        assert set(self._balanced_config().shell.allowed_commands) == set(POLICY_PRESETS["balanced"]["allowed_commands"])


# ---------------------------------------------------------------------------
# apply_policy_preset – experimental
# ---------------------------------------------------------------------------


class TestApplyPresetExperimental:
    def _exp_config(self) -> SafeCodeConfig:
        config = SafeCodeConfig(policy="experimental")
        apply_policy_preset(config)
        return config

    def test_allow_readonly_without_confirm_true(self):
        assert self._exp_config().shell.allow_readonly_without_confirm is True

    def test_require_confirm_for_medium_false(self):
        assert self._exp_config().shell.require_confirm_for_medium is False

    def test_block_high_risk_true(self):
        assert self._exp_config().shell.block_high_risk is True

    def test_network_disabled(self):
        assert self._exp_config().sandbox.network_enabled is False

    def test_allow_medium_after_apply_true(self):
        assert self._exp_config().hooks.allow_medium_after_apply is True

    def test_allowed_commands_matches_preset(self):
        assert set(self._exp_config().shell.allowed_commands) == set(POLICY_PRESETS["experimental"]["allowed_commands"])


# ---------------------------------------------------------------------------
# Alias equivalence
# ---------------------------------------------------------------------------


class TestAliasEquivalence:
    def _preset_config(self, policy: str) -> SafeCodeConfig:
        config = SafeCodeConfig(policy=policy)
        apply_policy_preset(config)
        return config

    def test_normal_equals_balanced_shell(self):
        n = self._preset_config("normal")
        b = self._preset_config("balanced")
        assert n.shell.allow_readonly_without_confirm == b.shell.allow_readonly_without_confirm
        assert n.shell.require_confirm_for_medium == b.shell.require_confirm_for_medium
        assert n.shell.block_high_risk == b.shell.block_high_risk
        assert set(n.shell.allowed_commands) == set(b.shell.allowed_commands)

    def test_normal_equals_balanced_sandbox(self):
        n = self._preset_config("normal")
        b = self._preset_config("balanced")
        assert n.sandbox.network_enabled == b.sandbox.network_enabled
        assert n.sandbox.restrict_to_project_root == b.sandbox.restrict_to_project_root

    def test_normal_equals_balanced_hooks(self):
        n = self._preset_config("normal")
        b = self._preset_config("balanced")
        assert n.hooks.allow_medium_after_apply == b.hooks.allow_medium_after_apply

    def test_learning_equals_experimental_shell(self):
        l = self._preset_config("learning")
        e = self._preset_config("experimental")
        assert l.shell.allow_readonly_without_confirm == e.shell.allow_readonly_without_confirm
        assert l.shell.require_confirm_for_medium == e.shell.require_confirm_for_medium
        assert set(l.shell.allowed_commands) == set(e.shell.allowed_commands)

    def test_learning_equals_experimental_hooks(self):
        l = self._preset_config("learning")
        e = self._preset_config("experimental")
        assert l.hooks.allow_medium_after_apply == e.hooks.allow_medium_after_apply


# ---------------------------------------------------------------------------
# Relative strictness comparisons
# ---------------------------------------------------------------------------


class TestRelativeStrictness:
    def _config(self, policy: str) -> SafeCodeConfig:
        c = SafeCodeConfig(policy=policy)
        apply_policy_preset(c)
        return c

    def test_strict_more_restrictive_than_balanced_readonly(self):
        assert self._config("strict").shell.allow_readonly_without_confirm is False
        assert self._config("balanced").shell.allow_readonly_without_confirm is True

    def test_strict_fewer_allowed_commands_than_balanced(self):
        strict_cmds = set(self._config("strict").shell.allowed_commands)
        balanced_cmds = set(self._config("balanced").shell.allowed_commands)
        assert strict_cmds < balanced_cmds

    def test_balanced_requires_confirm_for_medium_experimental_does_not(self):
        assert self._config("balanced").shell.require_confirm_for_medium is True
        assert self._config("experimental").shell.require_confirm_for_medium is False

    def test_balanced_fewer_allowed_commands_than_experimental(self):
        balanced_cmds = set(self._config("balanced").shell.allowed_commands)
        exp_cmds = set(self._config("experimental").shell.allowed_commands)
        assert balanced_cmds < exp_cmds

    def test_balanced_disallows_medium_hooks_experimental_allows(self):
        assert self._config("balanced").hooks.allow_medium_after_apply is False
        assert self._config("experimental").hooks.allow_medium_after_apply is True


# ---------------------------------------------------------------------------
# merge_trusted_config with preset-applied configs
# ---------------------------------------------------------------------------


class TestMergeWithPresets:
    def _preset_config(self, policy: str) -> SafeCodeConfig:
        c = SafeCodeConfig(policy=policy)
        apply_policy_preset(c)
        return c

    def test_user_strict_project_experimental_policy_stays_strict(self):
        merged = merge_trusted_config(self._preset_config("strict"), self._preset_config("experimental"))
        assert merged.policy == "strict"

    def test_user_strict_project_experimental_knobs_stay_strict(self):
        merged = merge_trusted_config(self._preset_config("strict"), self._preset_config("experimental"))
        assert merged.shell.allow_readonly_without_confirm is False
        assert merged.shell.require_confirm_for_medium is True
        assert merged.hooks.allow_medium_after_apply is False

    def test_user_strict_project_balanced_policy_stays_strict(self):
        merged = merge_trusted_config(self._preset_config("strict"), self._preset_config("balanced"))
        assert merged.policy == "strict"

    def test_user_balanced_project_experimental_policy_stays_balanced(self):
        merged = merge_trusted_config(self._preset_config("balanced"), self._preset_config("experimental"))
        assert merged.policy == "balanced"

    def test_user_balanced_project_experimental_require_confirm_stays_true(self):
        merged = merge_trusted_config(self._preset_config("balanced"), self._preset_config("experimental"))
        assert merged.shell.require_confirm_for_medium is True

    def test_user_balanced_project_experimental_medium_hook_stays_false(self):
        merged = merge_trusted_config(self._preset_config("balanced"), self._preset_config("experimental"))
        assert merged.hooks.allow_medium_after_apply is False

    def test_user_experimental_project_strict_policy_becomes_strict(self):
        merged = merge_trusted_config(self._preset_config("experimental"), self._preset_config("strict"))
        assert merged.policy == "strict"

    def test_user_experimental_project_strict_knobs_become_strict(self):
        merged = merge_trusted_config(self._preset_config("experimental"), self._preset_config("strict"))
        assert merged.shell.allow_readonly_without_confirm is False
        assert merged.shell.require_confirm_for_medium is True
        assert merged.hooks.allow_medium_after_apply is False

    def test_user_strict_project_strict_remains_strict(self):
        merged = merge_trusted_config(self._preset_config("strict"), self._preset_config("strict"))
        assert merged.policy == "strict"
        assert merged.shell.allow_readonly_without_confirm is False

    def test_user_experimental_project_experimental_remains_experimental(self):
        merged = merge_trusted_config(self._preset_config("experimental"), self._preset_config("experimental"))
        assert merged.policy == "experimental"
        assert merged.shell.require_confirm_for_medium is False
        assert merged.hooks.allow_medium_after_apply is True


# ---------------------------------------------------------------------------
# Alias names flow through merge correctly
# ---------------------------------------------------------------------------


class TestAliasesThroughMerge:
    def _alias_config(self, policy: str) -> SafeCodeConfig:
        c = SafeCodeConfig(policy=policy)
        apply_policy_preset(c)
        return c

    def test_user_strict_project_normal_policy_stays_strict(self):
        merged = merge_trusted_config(self._alias_config("strict"), self._alias_config("normal"))
        assert merged.policy == "strict"

    def test_user_normal_project_learning_policy_stays_normal(self):
        merged = merge_trusted_config(self._alias_config("normal"), self._alias_config("learning"))
        assert merged.policy == "normal"

    def test_user_learning_project_strict_policy_becomes_strict(self):
        merged = merge_trusted_config(self._alias_config("learning"), self._alias_config("strict"))
        assert merged.policy == "strict"


# ---------------------------------------------------------------------------
# SAFECODE_POLICY env var cannot lower effective safety
# ---------------------------------------------------------------------------


class TestSafecodePolicyEnv:
    def test_env_cannot_lower_strict_to_balanced(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAFECODE_POLICY", "balanced")
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user_config.toml"))
        (tmp_path / "user_config.toml").write_text('policy = "strict"\n', encoding="utf-8")
        (tmp_path / ".sac").mkdir()
        config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "strict"

    def test_env_can_raise_balanced_to_strict(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAFECODE_POLICY", "strict")
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user_config.toml"))
        (tmp_path / "user_config.toml").write_text('policy = "balanced"\n', encoding="utf-8")
        (tmp_path / ".sac").mkdir()
        config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "strict"

    def test_env_cannot_lower_strict_to_experimental(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAFECODE_POLICY", "experimental")
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user_config.toml"))
        (tmp_path / "user_config.toml").write_text('policy = "strict"\n', encoding="utf-8")
        (tmp_path / ".sac").mkdir()
        config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "strict"

    def test_env_cannot_lower_via_legacy_alias(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAFECODE_POLICY", "learning")
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user_config.toml"))
        (tmp_path / "user_config.toml").write_text('policy = "strict"\n', encoding="utf-8")
        (tmp_path / ".sac").mkdir()
        config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "strict"


# ---------------------------------------------------------------------------
# SafeCodeConfig.load applies the selected preset
# ---------------------------------------------------------------------------


class TestLoadAppliesPolicyPreset:
    def _write_project_config(self, tmp_path, text: str) -> None:
        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        (sac_dir / "config.toml").write_text(text, encoding="utf-8")

    def test_load_strict_actually_narrows_allowed_commands(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "missing-user.toml"))
        self._write_project_config(tmp_path, 'policy = "strict"\n')

        config = SafeCodeConfig.load(tmp_path)

        assert config.policy == "strict"
        assert config.shell.allowed_commands == ["git", "ls", "pwd"]
        assert "echo" not in config.shell.allowed_commands
        assert config.shell.allow_readonly_without_confirm is False

    def test_load_experimental_widens_allowed_commands_when_user_allows_it(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user_config.toml"))
        (tmp_path / "user_config.toml").write_text('policy = "experimental"\n', encoding="utf-8")
        self._write_project_config(tmp_path, 'policy = "experimental"\n')

        config = SafeCodeConfig.load(tmp_path)

        assert config.policy == "experimental"
        assert config.shell.allowed_commands == ["cat", "echo", "find", "git", "grep", "ls", "pwd"]
        assert config.shell.require_confirm_for_medium is False
        assert config.hooks.allow_medium_after_apply is True

    def test_env_strict_overrides_balanced_at_load(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user_config.toml"))
        monkeypatch.setenv("SAFECODE_POLICY", "strict")
        (tmp_path / "user_config.toml").write_text('policy = "balanced"\n', encoding="utf-8")
        self._write_project_config(tmp_path, 'policy = "balanced"\n')

        config = SafeCodeConfig.load(tmp_path)

        assert config.policy == "strict"
        assert config.shell.allowed_commands == ["git", "ls", "pwd"]

    def test_load_preserves_trusted_two_sided_network_opt_in(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user_config.toml"))
        config_text = (
            'policy = "balanced"\n'
            "\n"
            "[sandbox]\n"
            "network_enabled = true\n"
            'network_allowlist = ["api.openai.com"]\n'
        )
        (tmp_path / "user_config.toml").write_text(config_text, encoding="utf-8")
        self._write_project_config(tmp_path, config_text)

        config = SafeCodeConfig.load(tmp_path)

        assert config.sandbox.network_enabled is True
        assert config.sandbox.network_allowlist == ["api.openai.com"]

    def test_load_without_explicit_policy_preserves_user_shell_overrides(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user_config.toml"))
        (tmp_path / "user_config.toml").write_text(
            '[shell]\nallowed_commands = ["pytest"]\nrequire_confirm_for_medium = false\n',
            encoding="utf-8",
        )
        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        (sac_dir / "config.toml").write_text(
            '[shell]\nallowed_commands = ["pytest"]\nrequire_confirm_for_medium = false\n',
            encoding="utf-8",
        )

        config = SafeCodeConfig.load(tmp_path)

        assert config.shell.allowed_commands == ["pytest"]
        assert config.shell.require_confirm_for_medium is False


# ---------------------------------------------------------------------------
# Network isolation: project config cannot enable network if user disables it
# ---------------------------------------------------------------------------


class TestNetworkIsolation:
    def test_project_cannot_enable_network_if_user_disables(self):
        user = SafeCodeConfig(policy="strict")
        apply_policy_preset(user)
        project = SafeCodeConfig(policy="experimental")
        apply_policy_preset(project)
        project.sandbox.network_enabled = True  # project tries to enable

        merged = merge_trusted_config(user, project)
        assert merged.sandbox.network_enabled is False

    def test_project_cannot_enable_network_regardless_of_preset(self):
        user = SafeCodeConfig()
        user.sandbox.network_enabled = False
        project = SafeCodeConfig()
        project.sandbox.network_enabled = True

        merged = merge_trusted_config(user, project)
        assert merged.sandbox.network_enabled is False

    def test_both_enabled_stays_enabled(self):
        user = SafeCodeConfig()
        user.sandbox.network_enabled = True
        project = SafeCodeConfig()
        project.sandbox.network_enabled = True

        merged = merge_trusted_config(user, project)
        assert merged.sandbox.network_enabled is True


# ---------------------------------------------------------------------------
# Backward compatibility: "normal" and "learning" still work in load()
# ---------------------------------------------------------------------------


class TestBackwardCompatLoad:
    def test_normal_policy_loads(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user.toml"))
        (tmp_path / "user.toml").write_text('policy = "normal"\n', encoding="utf-8")
        (tmp_path / ".sac").mkdir()
        config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "normal"

    def test_learning_policy_loads(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user.toml"))
        (tmp_path / "user.toml").write_text('policy = "learning"\n', encoding="utf-8")
        sac_dir = tmp_path / ".sac"
        sac_dir.mkdir()
        # Give the project config the same policy so merge doesn't upgrade it.
        (sac_dir / "config.toml").write_text('policy = "learning"\n', encoding="utf-8")
        config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "learning"

    def test_strict_policy_loads(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAFECODE_USER_CONFIG", str(tmp_path / "user.toml"))
        (tmp_path / "user.toml").write_text('policy = "strict"\n', encoding="utf-8")
        (tmp_path / ".sac").mkdir()
        config = SafeCodeConfig.load(tmp_path)
        assert config.policy == "strict"


# ---------------------------------------------------------------------------
# apply_policy_preset with unknown policy name is a no-op
# ---------------------------------------------------------------------------


class TestUnknownPolicyPreset:
    def test_unknown_policy_leaves_config_unchanged(self):
        config = SafeCodeConfig(policy="custom_unknown")
        before = config.model_dump()
        apply_policy_preset(config)
        assert config.model_dump() == before
