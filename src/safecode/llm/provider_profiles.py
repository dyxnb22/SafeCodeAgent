"""User-level provider profile store for SafeCode Agent (v4.14.0).

Provider profiles live in [providers.<name>] tables inside the trusted user
config (~/.safecode/config.toml or SAFECODE_USER_CONFIG in tests).

Profiles are user-level ONLY.  Project-local config may NOT store credentials or
define providers, and cannot widen user-level network policy.

Resolution order for LLM config (highest priority first):
  1. Explicit env vars (SAFECODE_LLM_PROVIDER, SAFECODE_LLM_MODEL,
     provider-specific key env vars like DEEPSEEK_API_KEY)
  2. Active provider profile / default model
  3. Legacy [llm] table in user config
  4. Built-in defaults (mock provider)

Secrets are never written to project-local config and are redacted from all
normal output and logs.

All surfaces in this module are EXPERIMENTAL and carry no stable contract.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Built-in provider presets
# ---------------------------------------------------------------------------

_DEEPSEEK_ALIASES: dict[str, str] = {
    "flash": "deepseek-v4-flash",
    "pro": "deepseek-v4-pro",
}

def _levenshtein_distance(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(
                prev[j + 1] + 1,
                curr[j] + 1,
                prev[j] + (0 if ca == cb else 1),
            ))
        prev = curr
    return prev[-1]


def _fuzzy_match(query: str, candidates: list[str], *, max_distance: int = 2) -> str | None:
    """Return the closest candidate within max_distance, or None.

    When multiple candidates have the same distance, the first one wins.
    """
    if not query or not candidates:
        return None
    best: tuple[str, int] | None = None
    for c in candidates:
        d = _levenshtein_distance(query.lower(), c.lower())
        if d <= max_distance and (best is None or d < best[1]):
            best = (c, d)
    return best[0] if best is not None else None


def _collect_known_model_ids(profile: ProviderProfile | None = None) -> list[str]:
    """Collect all known model IDs from preset aliases and active profile."""
    ids: list[str] = []
    # Built-in deepseek aliases
    ids.extend(_DEEPSEEK_ALIASES.values())
    # Active profile aliases
    if profile is not None:
        ids.extend(profile.model_aliases.values())
        if profile.default_model:
            ids.append(profile.default_model)
    return sorted(set(ids))


def _fuzzy_match_model(query: str, profile: ProviderProfile | None = None) -> str | None:
    """Fuzzy-match a model ID against known model IDs."""
    candidates = _collect_known_model_ids(profile)
    return _fuzzy_match(query, candidates)


def _fuzzy_match_provider(query: str) -> str | None:
    """Fuzzy-match a provider name against supported providers."""
    candidates = sorted(SUPPORTED_PROVIDERS)
    return _fuzzy_match(query, candidates)

# Preset values for known providers: used by `sac provider add <name>`.
_PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-flash",
        "model_aliases": _DEEPSEEK_ALIASES,
        "network_allowlist": ["api.deepseek.com"],
        "api_key_env": "DEEPSEEK_API_KEY",
    },
}

SUPPORTED_PROVIDERS: frozenset[str] = frozenset(_PROVIDER_PRESETS) | frozenset({
    "openai", "openai-compatible", "anthropic", "mock"
})


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class ProviderProfile(BaseModel):
    """User-level provider profile persisted to trusted user config."""

    name: str
    base_url: str = ""
    # api_key is stored in user-level config only.  Project config cannot set this.
    api_key: str | None = None
    default_model: str = ""
    model_aliases: dict[str, str] = Field(default_factory=dict)
    network_allowlist: list[str] = Field(default_factory=list)

    def resolve_model(self, alias: str) -> tuple[str, str | None]:
        """Resolve alias/scoped-name to (model_id, suggestion).

        Accepts:
          - "flash", "pro"         -> alias lookup in model_aliases
          - "deepseek:flash"       -> strip provider prefix, then alias lookup
          - "deepseek-v4-flash"    -> returned as-is
          - ""                     -> returns self.default_model

        Returns (resolved_model_id, fuzzy_suggestion_or_None).
        """
        if not alias:
            return self.default_model, None
        # Strip provider prefix ("deepseek:flash" -> "flash")
        if ":" in alias:
            _prefix, _, alias = alias.partition(":")
        resolved = self.model_aliases.get(alias, alias)
        # Check if resolved looks like a known model ID already
        known_ids = set(self.model_aliases.values())
        if self.default_model:
            known_ids.add(self.default_model)
        known_ids.update(_DEEPSEEK_ALIASES.values())
        if resolved in known_ids:
            return resolved, None
        # Fuzzy match against known model IDs
        fuzzy = _fuzzy_match_model(resolved, self)
        if fuzzy and fuzzy != resolved:
            return fuzzy, f"Did you mean '{fuzzy}'? (from '{alias}')"
        return resolved, None

    def api_key_source(self) -> str:
        """Return redacted credential source description (never the raw key)."""
        preset = _PROVIDER_PRESETS.get(self.name, {})
        env_var = preset.get("api_key_env", "")
        if env_var and os.getenv(env_var):
            return f"env:{env_var}"
        try:
            from safecode.security.keychain import get_api_key
            if get_api_key(self.name):
                return "keychain"
        except Exception:
            pass
        if self.api_key:
            return "user-config"
        return "missing"

    def effective_api_key(self) -> str | None:
        """Env var takes precedence over keychain, then stored api_key."""
        preset = _PROVIDER_PRESETS.get(self.name, {})
        env_var = preset.get("api_key_env", "")
        if env_var:
            key = os.getenv(env_var)
            if key:
                return key
        try:
            from safecode.security.keychain import get_api_key
            key = get_api_key(self.name)
            if key:
                return key
        except Exception:
            pass
        return self.api_key


# ---------------------------------------------------------------------------
# Profile store helpers
# ---------------------------------------------------------------------------

def _load_user_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_profiles(config_path: Path | None = None) -> dict[str, ProviderProfile]:
    """Load all provider profiles from the trusted user config.

    Returns a dict of {name: ProviderProfile}.
    """
    from safecode.config import _user_config_path
    path = (config_path or _user_config_path()).expanduser()
    data = _load_user_toml(path)
    raw_providers = data.get("providers", {})
    profiles: dict[str, ProviderProfile] = {}
    for key, value in raw_providers.items():
        if key == "active" or not isinstance(value, dict):
            continue
        try:
            profiles[key] = ProviderProfile(
                name=key,
                base_url=str(value.get("base_url", "")),
                api_key=value.get("api_key") or None,
                default_model=str(value.get("default_model", "")),
                model_aliases=dict(value.get("model_aliases", {})),
                network_allowlist=list(value.get("network_allowlist", [])),
            )
        except Exception:
            pass
    return profiles


def get_active_profile_name(config_path: Path | None = None) -> str | None:
    """Return the name of the active provider profile, or None."""
    from safecode.config import _user_config_path
    path = (config_path or _user_config_path()).expanduser()
    data = _load_user_toml(path)
    providers = data.get("providers", {})
    name = providers.get("active")
    if isinstance(name, str) and name:
        return name
    return None


def get_active_profile(config_path: Path | None = None) -> ProviderProfile | None:
    """Return the active ProviderProfile, or None if none is active."""
    name = get_active_profile_name(config_path)
    if not name:
        return None
    profiles = load_profiles(config_path)
    return profiles.get(name)


def resolve_model_in_active_profile(alias: str, config_path: Path | None = None) -> str | None:
    """Resolve a model alias/name using the active provider profile.

    Returns the resolved model ID, or None if no profile is active.
    """
    profile = get_active_profile(config_path)
    if profile is None:
        return None
    resolved, _hint = profile.resolve_model(alias)
    return resolved


def save_profile(profile: ProviderProfile, config_path: Path | None = None) -> Path:
    """Persist a provider profile to the trusted user config.

    Reads existing config, updates the [providers.<name>] section, and
    writes back. Only updates providers section; other sections untouched.
    Never writes to project-local config.
    """
    from safecode.config import _user_config_path
    path = (config_path or _user_config_path()).expanduser()
    data = _load_user_toml(path)

    providers = dict(data.get("providers", {}))
    profile_data: dict[str, Any] = {
        "base_url": profile.base_url,
        "default_model": profile.default_model,
        "model_aliases": profile.model_aliases,
        "network_allowlist": profile.network_allowlist,
    }
    if profile.api_key is not None:
        profile_data["api_key"] = profile.api_key
    providers[profile.name] = profile_data
    data["providers"] = providers

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_user_toml(data), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def set_active_provider(name: str, config_path: Path | None = None) -> Path:
    """Set the active provider in user config."""
    from safecode.config import _user_config_path
    path = (config_path or _user_config_path()).expanduser()
    data = _load_user_toml(path)
    providers = dict(data.get("providers", {}))
    providers["active"] = name
    data["providers"] = providers
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_user_toml(data), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def remove_profile(name: str, config_path: Path | None = None) -> bool:
    """Remove a provider profile from user config.  Returns True if removed."""
    from safecode.config import _user_config_path
    path = (config_path or _user_config_path()).expanduser()
    data = _load_user_toml(path)
    providers = dict(data.get("providers", {}))
    if name not in providers:
        return False
    del providers[name]
    # If removed profile was active, clear active
    if providers.get("active") == name:
        del providers["active"]
    data["providers"] = providers
    path.write_text(_render_user_toml(data), encoding="utf-8")
    return True


def make_deepseek_profile(api_key: str | None = None) -> ProviderProfile:
    """Return a ProviderProfile pre-filled with DeepSeek preset defaults."""
    preset = _PROVIDER_PRESETS["deepseek"]
    return ProviderProfile(
        name="deepseek",
        base_url=preset["base_url"],
        api_key=api_key,
        default_model=preset["default_model"],
        model_aliases=dict(preset["model_aliases"]),
        network_allowlist=list(preset["network_allowlist"]),
    )


# ---------------------------------------------------------------------------
# TOML writer
# ---------------------------------------------------------------------------

def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        pairs = ", ".join(f'{k} = {_toml_value(v)}' for k, v in sorted(value.items()))
        return "{" + pairs + "}"
    if value is None:
        return '""'
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _render_user_toml(data: dict[str, Any]) -> str:
    """Render user config dict to TOML, handling [providers.<name>] nesting."""
    lines: list[str] = []

    # Top-level scalar keys (alphabetical, skip dict sections)
    scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    for key in sorted(scalars):
        lines.append(f"{key} = {_toml_value(scalars[key])}")
    if scalars:
        lines.append("")

    # Regular dict sections — but handle "providers" specially
    regular_sections = {k: v for k, v in data.items() if isinstance(v, dict) and k != "providers"}
    for section in sorted(regular_sections):
        lines.append(f"[{section}]")
        for key in sorted(regular_sections[section]):
            lines.append(f"{key} = {_toml_value(regular_sections[section][key])}")
        lines.append("")

    # Providers section: [providers] for active, then [providers.<name>] for each profile
    providers = data.get("providers")
    if providers:
        # Top-level providers keys (like "active") — emit as [providers]
        provider_scalars = {k: v for k, v in providers.items() if not isinstance(v, dict)}
        if provider_scalars:
            lines.append("[providers]")
            for key in sorted(provider_scalars):
                lines.append(f"{key} = {_toml_value(provider_scalars[key])}")
            lines.append("")
        # Each named profile
        for profile_name in sorted(k for k, v in providers.items() if isinstance(v, dict)):
            lines.append(f"[providers.{profile_name}]")
            profile_dict = providers[profile_name]
            for key in sorted(profile_dict):
                lines.append(f"{key} = {_toml_value(profile_dict[key])}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"
