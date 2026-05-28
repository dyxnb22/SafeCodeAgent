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
        """Load config from env and .sac/config.toml, falling back to defaults."""
        config_path = project_root / ".sac" / "config.toml"
        data: dict = {}
        if config_path.exists():
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))

        config = cls(**data)
        env_policy = os.getenv("SAFECODE_POLICY")
        if env_policy:
            config.policy = env_policy
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
