"""Project setup wizard helpers (v2.3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from safecode.config import SafeCodeConfig


@dataclass(frozen=True)
class SetupResult:
    """Files and settings produced by setup."""

    config_path: Path
    env_path: Path
    provider: str
    model: str
    policy: str
    network_enabled: bool
    approval_dir: Path
    sandbox_approval_dir: Path


def write_setup(
    project_root: Path,
    *,
    provider: str = "mock",
    model: str = "gpt-4.1-mini",
    policy: str = "normal",
    network_enabled: bool = False,
    approval_dir: Path | None = None,
    sandbox_approval_dir: Path | None = None,
    force: bool = False,
) -> SetupResult:
    """Write SafeCode project config plus approval-dir environment hints."""
    if policy not in {"learning", "normal", "strict"}:
        raise ValueError("policy must be one of: learning, normal, strict")
    if provider not in {"mock", "openai"}:
        raise ValueError("provider must be one of: mock, openai")

    sac_dir = project_root / ".sac"
    config_path = sac_dir / "config.toml"
    env_path = sac_dir / "setup.env"
    if not force and (config_path.exists() or env_path.exists()):
        raise FileExistsError("SafeCode setup files already exist. Re-run with --force to overwrite.")

    approval_dir = (approval_dir or (Path.home() / ".safecode" / "approvals")).expanduser()
    sandbox_approval_dir = (sandbox_approval_dir or (Path.home() / ".safecode" / "sandbox-approvals")).expanduser()
    approval_dir.mkdir(parents=True, exist_ok=True)
    sandbox_approval_dir.mkdir(parents=True, exist_ok=True)

    config = SafeCodeConfig()
    config.policy = policy
    config.sandbox.network_enabled = network_enabled
    config.llm.provider = provider
    config.llm.model = model

    sac_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config.to_toml(), encoding="utf-8")
    env_path.write_text(
        "\n".join(
            [
                "# Source this file when you want SafeCode approvals outside the project tree.",
                f'SAFECODE_APPROVAL_DIR="{approval_dir}"',
                f'SAFECODE_SANDBOX_APPROVAL_DIR="{sandbox_approval_dir}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return SetupResult(
        config_path=config_path,
        env_path=env_path,
        provider=provider,
        model=model,
        policy=policy,
        network_enabled=network_enabled,
        approval_dir=approval_dir,
        sandbox_approval_dir=sandbox_approval_dir,
    )
