"""Application configuration for SafeCode Agent."""

import os
import tomllib
import warnings
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field


class ShellPolicy(BaseModel):
    """Policy for command execution."""

    default_timeout_seconds: int = 30
    allow_readonly_without_confirm: bool = True
    require_confirm_for_medium: bool = True
    block_high_risk: bool = True
    allowed_commands: list[str] = Field(default_factory=lambda: ["pwd", "ls", "echo", "git"])


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
    allow_medium_after_apply: bool = False


class LLMConfig(BaseModel):
    """LLM provider configuration.

    Supported provider keys: ``mock`` (default), ``openai``, ``openai-compatible``,
    ``anthropic``, ``deepseek`` (EXPERIMENTAL).
    """

    provider: str = "mock"
    model: str = "gpt-4.1-mini"
    base_url: str = "https://api.openai.com/v1/chat/completions"

    # Optional fallback provider activated on hard transport failures from the primary.
    # Both primary and fallback are subject to the same network policy checks.
    # Recoverable contract failures and policy blocks do not trigger the fallback.
    fallback_provider: str | None = None
    fallback_model: str | None = None
    fallback_base_url: str | None = None


class TrustRoot(BaseModel):
    """User-level per-directory trust declaration."""

    path: str
    policy: str = "balanced"
    include_subdirectories: bool = True


class TrustConfig(BaseModel):
    """Trust declarations. Only user-level config may grant trust."""

    roots: list[TrustRoot] = Field(default_factory=list)


class SafeCodeConfig(BaseModel):
    """Runtime configuration with safe defaults."""

    sac_dir: str = ".sac"
    max_tree_files: int = 200
    max_file_lines: int = 300
    max_file_bytes: int = 200_000
    max_context_chars: int = 40_000
    policy: str = "balanced"
    shell: ShellPolicy = Field(default_factory=ShellPolicy)
    sandbox: SandboxPolicy = Field(default_factory=SandboxPolicy)
    hooks: HookConfig = Field(default_factory=HookConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    trust: TrustConfig = Field(default_factory=TrustConfig)

    @classmethod
    def load(cls, project_root: Path) -> "SafeCodeConfig":
        """Load trusted user config first, then merge project config safely."""
        user_data = _read_toml(_user_config_path())
        project_data = _read_toml(project_root / ".sac" / "config.toml")
        user_config = cls(**user_data)
        project_config = cls(**project_data)
        config = merge_trusted_config(user_config, project_config)
        env_policy = os.getenv("SAFECODE_POLICY")
        apply_selected_preset = "policy" in user_data or "policy" in project_data
        if env_policy:
            if is_known_policy_name(env_policy):
                config.policy = _stricter_policy(config.policy, env_policy)
                apply_selected_preset = True
            else:
                warnings.warn(
                    f"SAFECODE_POLICY={env_policy!r} is not a recognized policy name "
                    f"(known: {sorted(KNOWN_POLICY_NAMES)}); ignoring.",
                    UserWarning,
                    stacklevel=2,
                )
        # Presets provide safe defaults, but network access remains a separate
        # trusted two-sided opt-in computed by merge_trusted_config().
        network_enabled = config.sandbox.network_enabled
        network_allowlist = list(config.sandbox.network_allowlist)
        if apply_selected_preset:
            apply_policy_preset(config)
            if network_enabled:
                config.sandbox.network_enabled = True
            if network_allowlist:
                config.sandbox.network_allowlist = network_allowlist
        env_provider = os.getenv("SAFECODE_LLM_PROVIDER")
        if env_provider:
            config.llm.provider = env_provider
        env_model = os.getenv("SAFECODE_LLM_MODEL")
        if env_model:
            config.llm.model = env_model
        return config

    def to_toml(self) -> str:
        """Render a small TOML config without adding a TOML dependency."""
        after_apply = ", ".join(f'"{command}"' for command in self.hooks.after_apply)
        allowlist = ", ".join(f'"{host}"' for host in self.sandbox.network_allowlist)
        sensitive = ", ".join(f'"{name}"' for name in self.sandbox.sensitive_names)
        allowed_commands = ", ".join(f'"{command}"' for command in self.shell.allowed_commands)
        return (
            f'sac_dir = "{self.sac_dir}"\n'
            f"max_tree_files = {self.max_tree_files}\n"
            f"max_file_lines = {self.max_file_lines}\n"
            f"max_file_bytes = {self.max_file_bytes}\n"
            f"max_context_chars = {self.max_context_chars}\n"
            f'policy = "{self.policy}"\n\n'
            "[shell]\n"
            f"default_timeout_seconds = {self.shell.default_timeout_seconds}\n"
            f"allow_readonly_without_confirm = {str(self.shell.allow_readonly_without_confirm).lower()}\n"
            f"require_confirm_for_medium = {str(self.shell.require_confirm_for_medium).lower()}\n"
            f"block_high_risk = {str(self.shell.block_high_risk).lower()}\n\n"
            f"allowed_commands = [{allowed_commands}]\n\n"
            "[sandbox]\n"
            f"restrict_to_project_root = {str(self.sandbox.restrict_to_project_root).lower()}\n"
            f"network_enabled = {str(self.sandbox.network_enabled).lower()}\n"
            f"network_allowlist = [{allowlist}]\n"
            f"sensitive_names = [{sensitive}]\n\n"
            "[hooks]\n"
            f"after_apply = [{after_apply}]\n\n"
            f"allow_medium_after_apply = {str(self.hooks.allow_medium_after_apply).lower()}\n\n"
            "[llm]\n"
            f'provider = "{self.llm.provider}"\n'
            f'model = "{self.llm.model}"\n'
            f'base_url = "{self.llm.base_url}"\n'
        )


def ensure_config_file(project_root: Path) -> Path:
    """Create a default .sac/config.toml when it does not already exist."""
    config_path = project_root / ".sac" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(SafeCodeConfig().to_toml(), encoding="utf-8")
    return config_path


_POLICY_ALIASES: dict[str, str] = {"normal": "balanced", "learning": "experimental"}

POLICY_ORDER: dict[str, int] = {
    "experimental": 0,
    "learning": 0,
    "balanced": 1,
    "normal": 1,
    "strict": 2,
}

# All recognized policy names (canonical + aliases). Unknown names are treated as
# balanced-equivalent for ordering but never silently override a known name.
KNOWN_POLICY_NAMES: frozenset[str] = frozenset(POLICY_ORDER)


def is_known_policy_name(name: str) -> bool:
    """Return True if name is a recognized canonical policy name or legacy alias."""
    return name in KNOWN_POLICY_NAMES

# Preset knob values keyed by canonical policy name.
# Keys: shell.*, sandbox.restrict_to_project_root, sandbox.network_enabled,
#        sandbox.network_allowlist, hooks.allow_medium_after_apply
POLICY_PRESETS: dict[str, dict] = {
    "strict": {
        "allow_readonly_without_confirm": False,
        "require_confirm_for_medium": True,
        "block_high_risk": True,
        "allowed_commands": ["git", "ls", "pwd"],
        "restrict_to_project_root": True,
        "network_enabled": False,
        "network_allowlist": [],
        "allow_medium_after_apply": False,
    },
    "balanced": {
        "allow_readonly_without_confirm": True,
        "require_confirm_for_medium": True,
        "block_high_risk": True,
        "allowed_commands": ["echo", "git", "ls", "pwd"],
        "restrict_to_project_root": True,
        "network_enabled": False,
        "network_allowlist": [],
        "allow_medium_after_apply": False,
    },
    "experimental": {
        "allow_readonly_without_confirm": True,
        "require_confirm_for_medium": False,
        "block_high_risk": True,
        "allowed_commands": ["cat", "echo", "find", "git", "grep", "ls", "pwd"],
        "restrict_to_project_root": True,
        "network_enabled": False,
        "network_allowlist": [],
        "allow_medium_after_apply": True,
    },
}


def normalize_policy_name(name: str) -> str:
    """Resolve policy alias to canonical name (normal→balanced, learning→experimental)."""
    return _POLICY_ALIASES.get(name, name)


def apply_policy_preset(config: SafeCodeConfig) -> None:
    """Apply preset knob values for config.policy in-place.

    Unconditionally sets shell/sandbox/hooks knobs to the values defined by the
    canonical policy preset.  Callers that want to preserve explicitly stricter
    TOML values should snapshot those fields before calling and re-enforce them
    after with the merge helpers.
    """
    canonical = normalize_policy_name(config.policy)
    p = POLICY_PRESETS.get(canonical)
    if p is None:
        return
    config.shell.allow_readonly_without_confirm = p["allow_readonly_without_confirm"]
    config.shell.require_confirm_for_medium = p["require_confirm_for_medium"]
    config.shell.block_high_risk = p["block_high_risk"]
    config.shell.allowed_commands = list(p["allowed_commands"])
    config.sandbox.restrict_to_project_root = p["restrict_to_project_root"]
    config.sandbox.network_enabled = p["network_enabled"]
    config.sandbox.network_allowlist = list(p["network_allowlist"])
    config.hooks.allow_medium_after_apply = p["allow_medium_after_apply"]


def merge_trusted_config(user_config: SafeCodeConfig, project_config: SafeCodeConfig) -> SafeCodeConfig:
    """Merge configs so project config cannot lower user-level safety."""
    merged = user_config.model_copy(deep=True)
    merged.sac_dir = project_config.sac_dir or user_config.sac_dir
    merged.max_tree_files = min(user_config.max_tree_files, project_config.max_tree_files)
    merged.max_file_lines = min(user_config.max_file_lines, project_config.max_file_lines)
    merged.max_file_bytes = min(user_config.max_file_bytes, project_config.max_file_bytes)
    merged.max_context_chars = min(user_config.max_context_chars, project_config.max_context_chars)
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
    merged.shell.allowed_commands = sorted(set(user_config.shell.allowed_commands) & set(project_config.shell.allowed_commands))
    if not merged.shell.allowed_commands:
        merged.shell.allowed_commands = sorted(set(user_config.shell.allowed_commands))

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
    merged.hooks.allow_medium_after_apply = (
        user_config.hooks.allow_medium_after_apply and project_config.hooks.allow_medium_after_apply
    )
    merged.llm = user_config.llm.model_copy(deep=True)
    merged.trust = user_config.trust.model_copy(deep=True)
    return merged


_EPHEMERAL_TRUST_GRANTS: dict[str, TrustRoot] = {}


def grant_ephemeral_trust(path: Path, policy: str = "balanced") -> str:
    """Grant process-local trust until this Python process exits."""
    grant = TrustRoot(path=str(path.expanduser().resolve()), policy=policy, include_subdirectories=True)
    grant_id = uuid4().hex
    _EPHEMERAL_TRUST_GRANTS[grant_id] = grant
    return grant_id


def revoke_ephemeral_trust(grant_id: str) -> bool:
    """Revoke a process-local trust grant."""
    return _EPHEMERAL_TRUST_GRANTS.pop(grant_id, None) is not None


def clear_ephemeral_trust() -> int:
    """Clear all process-local trust grants; primarily useful for tests/session teardown."""
    count = len(_EPHEMERAL_TRUST_GRANTS)
    _EPHEMERAL_TRUST_GRANTS.clear()
    return count


def effective_trust_for_path(project_root: Path, target_path: Path | None = None) -> dict:
    """Return audited effective trust state for a path.

    Project-local config is intentionally ignored for trust grants. User-level
    roots and process-local ephemeral roots can only keep or strengthen the
    effective policy; they never bypass approval, audit, rollback, checkpoint,
    redaction, or command policy.
    """
    root = project_root.resolve()
    target = (target_path or project_root).expanduser().resolve()
    data = _read_toml(project_root / ".sac" / "config.toml")
    attempted_project_trust = "trust" in data
    config = SafeCodeConfig.load(project_root)
    matched: list[TrustRoot] = []
    for trust_root in [*config.trust.roots, *_EPHEMERAL_TRUST_GRANTS.values()]:
        if _trust_root_matches(trust_root, target):
            matched.append(trust_root)

    effective_policy = config.policy
    for match in matched:
        effective_policy = _stricter_policy(effective_policy, match.policy)
    result = {
        "trusted": bool(matched),
        "path": str(target),
        "project_root": str(root),
        "effective_policy": effective_policy,
        "matched_roots": [str(Path(item.path).expanduser()) for item in matched],
        "ephemeral_count": sum(1 for item in _EPHEMERAL_TRUST_GRANTS.values() if _trust_root_matches(item, target)),
        "project_trust_blocked": attempted_project_trust,
    }
    _audit_trust_lookup(project_root, result)
    return result


def _trust_root_matches(trust_root: TrustRoot, target: Path) -> bool:
    try:
        root = Path(trust_root.path).expanduser().resolve()
    except OSError:
        return False
    if target == root:
        return True
    if not trust_root.include_subdirectories:
        return False
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


def _audit_trust_lookup(project_root: Path, result: dict) -> None:
    from safecode.audit.logger import AuditLogger
    from safecode.audit.models import AuditEvent
    from safecode.utils.time import utc_now_iso

    AuditLogger(project_root, SafeCodeConfig.load(project_root)).write(
        AuditEvent(
            type="trust_config_lookup",
            timestamp=utc_now_iso(),
            status="blocked" if result["project_trust_blocked"] else "success",
            message="Project trust config blocked." if result["project_trust_blocked"] else "Trust config lookup completed.",
            metadata={
                "trusted": str(result["trusted"]).lower(),
                "effective_policy": str(result["effective_policy"]),
                "matched_root_count": str(len(result["matched_roots"])),
                "ephemeral_count": str(result["ephemeral_count"]),
                "project_trust_blocked": str(result["project_trust_blocked"]).lower(),
            },
        )
    )


def _stricter_policy(left: str, right: str) -> str:
    """Return the stricter policy name.

    Unknown names on the right (project config or env var) never override a
    known left-side name.  Unknown names on the left are compared conservatively
    as balanced-equivalent (order=1).
    """
    if right not in POLICY_ORDER:
        return left  # unknown right cannot override; always keep left
    if left not in POLICY_ORDER:
        # Unknown left: compare conservatively as balanced (1)
        return left if 1 >= POLICY_ORDER[right] else right
    return left if POLICY_ORDER[left] >= POLICY_ORDER[right] else right


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
