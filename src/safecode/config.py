"""Application configuration for SafeCode Agent."""

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class ShellPolicy(BaseModel):
    """Policy for command execution."""

    default_timeout_seconds: int = 30
    allow_readonly_without_confirm: bool = True
    require_confirm_for_medium: bool = True
    block_high_risk: bool = True


class SandboxPolicy(BaseModel):
    """Policy for filesystem and network containment."""

    restrict_to_project_root: bool = True
    network_enabled: bool = False
    network_allowlist: list[str] = Field(default_factory=list)
    sensitive_names: list[str] = Field(
        default_factory=lambda: [".env", ".ssh", ".aws", "id_rsa", "id_dsa", "credentials", "token"]
    )


class HookConfig(BaseModel):
    """Project hooks run by SafeCode after controlled operations."""

    after_apply: list[str] = Field(default_factory=list)


class SafeCodeConfig(BaseModel):
    """Runtime configuration with safe defaults."""

    sac_dir: str = ".sac"
    max_tree_files: int = 200
    max_file_lines: int = 300
    policy: str = "normal"
    shell: ShellPolicy = Field(default_factory=ShellPolicy)
    sandbox: SandboxPolicy = Field(default_factory=SandboxPolicy)
    hooks: HookConfig = Field(default_factory=HookConfig)

    @classmethod
    def load(cls, project_root: Path) -> "SafeCodeConfig":
        """Load trusted user config first, then merge project config safely."""
        user_config = cls(**_read_toml(_user_config_path()))
        project_config = cls(**_read_toml(project_root / ".sac" / "config.toml"))
        config = merge_trusted_config(user_config, project_config)
        env_policy = os.getenv("SAFECODE_POLICY")
        if env_policy:
            config.policy = _stricter_policy(config.policy, env_policy)
        return config

    def to_toml(self) -> str:
        """Render a small TOML config without adding a TOML dependency."""
        after_apply = ", ".join(f'"{command}"' for command in self.hooks.after_apply)
        allowlist = ", ".join(f'"{host}"' for host in self.sandbox.network_allowlist)
        sensitive = ", ".join(f'"{name}"' for name in self.sandbox.sensitive_names)
        return (
            f'sac_dir = "{self.sac_dir}"\n'
            f"max_tree_files = {self.max_tree_files}\n"
            f"max_file_lines = {self.max_file_lines}\n"
            f'policy = "{self.policy}"\n\n'
            "[shell]\n"
            f"default_timeout_seconds = {self.shell.default_timeout_seconds}\n"
            f"allow_readonly_without_confirm = {str(self.shell.allow_readonly_without_confirm).lower()}\n"
            f"require_confirm_for_medium = {str(self.shell.require_confirm_for_medium).lower()}\n"
            f"block_high_risk = {str(self.shell.block_high_risk).lower()}\n\n"
            "[sandbox]\n"
            f"restrict_to_project_root = {str(self.sandbox.restrict_to_project_root).lower()}\n"
            f"network_enabled = {str(self.sandbox.network_enabled).lower()}\n"
            f"network_allowlist = [{allowlist}]\n"
            f"sensitive_names = [{sensitive}]\n\n"
            "[hooks]\n"
            f"after_apply = [{after_apply}]\n"
        )


def ensure_config_file(project_root: Path) -> Path:
    """Create a default .sac/config.toml when it does not already exist."""
    config_path = project_root / ".sac" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(SafeCodeConfig().to_toml(), encoding="utf-8")
    return config_path


POLICY_ORDER = {"learning": 0, "normal": 1, "strict": 2}


def merge_trusted_config(user_config: SafeCodeConfig, project_config: SafeCodeConfig) -> SafeCodeConfig:
    """Merge configs so project config cannot lower user-level safety."""
    merged = user_config.model_copy(deep=True)
    merged.sac_dir = project_config.sac_dir or user_config.sac_dir
    merged.max_tree_files = min(user_config.max_tree_files, project_config.max_tree_files)
    merged.max_file_lines = min(user_config.max_file_lines, project_config.max_file_lines)
    merged.policy = _stricter_policy(user_config.policy, project_config.policy)

    merged.shell.default_timeout_seconds = min(
        user_config.shell.default_timeout_seconds,
        project_config.shell.default_timeout_seconds,
    )
    merged.shell.allow_readonly_without_confirm = (
        user_config.shell.allow_readonly_without_confirm and project_config.shell.allow_readonly_without_confirm
    )
    merged.shell.require_confirm_for_medium = (
        user_config.shell.require_confirm_for_medium or project_config.shell.require_confirm_for_medium
    )
    merged.shell.block_high_risk = user_config.shell.block_high_risk or project_config.shell.block_high_risk

    merged.sandbox.restrict_to_project_root = (
        user_config.sandbox.restrict_to_project_root or project_config.sandbox.restrict_to_project_root
    )
    merged.sandbox.network_enabled = user_config.sandbox.network_enabled and project_config.sandbox.network_enabled
    if user_config.sandbox.network_allowlist and project_config.sandbox.network_allowlist:
        merged.sandbox.network_allowlist = sorted(
            set(user_config.sandbox.network_allowlist) & set(project_config.sandbox.network_allowlist)
        )
    elif user_config.sandbox.network_allowlist:
        merged.sandbox.network_allowlist = list(user_config.sandbox.network_allowlist)
    else:
        merged.sandbox.network_allowlist = list(project_config.sandbox.network_allowlist)
    merged.sandbox.sensitive_names = sorted(
        set(user_config.sandbox.sensitive_names) | set(project_config.sandbox.sensitive_names)
    )

    merged.hooks.after_apply = list(project_config.hooks.after_apply)
    return merged


def _stricter_policy(left: str, right: str) -> str:
    """Return the stricter policy name."""
    return left if POLICY_ORDER.get(left, 1) >= POLICY_ORDER.get(right, 1) else right


def _user_config_path() -> Path:
    """Return the trusted user-level config path."""
    env_path = os.getenv("SAFECODE_USER_CONFIG")
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".safecode" / "config.toml"


def _read_toml(path: Path) -> dict:
    """Read TOML when present."""
    if path.exists():
        return tomllib.loads(path.read_text(encoding="utf-8"))
    return {}
