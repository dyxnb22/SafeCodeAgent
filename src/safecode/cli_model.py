"""User-level model configuration command (v4.14.0 enhanced with provider profiles)."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

import typer

from safecode.cli_shared import console
from safecode.config import SafeCodeConfig, _user_config_path
from safecode.context.redactor import redact_secrets

_KNOWN_PROVIDERS = {"mock", "openai", "openai-compatible", "anthropic", "deepseek"}
_DEFAULT_BASE_URLS: dict[str, str] = {
    "mock": "https://api.openai.com/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "openai-compatible": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "deepseek": "https://api.deepseek.com",
}

# Special model keywords handled before the old explicit-config path.
_MODEL_SPECIAL_KEYWORDS = frozenset({"list", "status"})


def _load_user_data(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if value is None:
        return '""'
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _render_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for key in sorted(k for k, v in data.items() if not isinstance(v, dict)):
        lines.append(f"{key} = {_toml_value(data[key])}")
    if lines:
        lines.append("")
    for section in sorted(k for k, v in data.items() if isinstance(v, dict)):
        lines.append(f"[{section}]")
        for key in sorted(data[section]):
            lines.append(f"{key} = {_toml_value(data[section][key])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_user_model_config(
    *,
    provider: str,
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    enable_user_network: bool | None = None,
    config_path: Path | None = None,
) -> Path:
    """Persist provider/model credentials to the trusted user config file."""
    provider = provider.strip().lower()
    if provider not in _KNOWN_PROVIDERS:
        raise ValueError(f"provider must be one of: {', '.join(sorted(_KNOWN_PROVIDERS))}")
    if not model.strip():
        raise ValueError("model must be non-empty")

    path = (config_path or _user_config_path()).expanduser()
    data = _load_user_data(path)
    llm = dict(data.get("llm", {}))
    llm["provider"] = provider
    llm["model"] = model.strip()
    llm["base_url"] = (base_url or _DEFAULT_BASE_URLS[provider]).strip()
    if api_key is not None:
        llm["api_key"] = api_key.strip()
    data["llm"] = llm

    if enable_user_network is not None:
        sandbox = dict(data.get("sandbox", {}))
        sandbox["network_enabled"] = enable_user_network
        data["sandbox"] = sandbox

    path.parent.mkdir(parents=True, exist_ok=True)
    # Use _render_user_toml to correctly handle [providers.<name>] nested sections.
    from safecode.llm.provider_profiles import _render_user_toml
    path.write_text(_render_user_toml(data), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def _render_model_status(config: SafeCodeConfig, path: Path) -> str:
    key_state = "configured" if config.llm.api_key else "not configured"
    from safecode.llm.provider_profiles import get_active_profile_name
    active_profile = get_active_profile_name(path)
    lines = [
        f"Config: {path}",
        f"Provider: {config.llm.provider}",
        f"Model: {config.llm.model}",
        f"Base URL: {config.llm.base_url}",
        f"API key: {key_state}",
        f"User network: {str(config.sandbox.network_enabled).lower()}",
    ]
    if active_profile:
        lines.append(f"Active profile: {active_profile}")
    return redact_secrets("\n".join(lines))


def _render_model_list(project_root: Path, path: Path) -> str:
    """Return available model aliases for the active provider profile."""
    from safecode.llm.provider_profiles import get_active_profile
    profile = get_active_profile(path)
    if profile is None:
        return (
            "No active provider profile configured.\n"
            "Run: sac provider add deepseek"
        )
    lines = [
        f"Provider: {profile.name}",
        f"Default model: {profile.default_model}",
        "Aliases:",
    ]
    if profile.model_aliases:
        for alias, model_id in sorted(profile.model_aliases.items()):
            config = SafeCodeConfig.load(project_root)
            marker = " [active]" if config.llm.model == model_id else ""
            lines.append(f"  {alias:12s} -> {model_id}{marker}")
    else:
        lines.append("  (no aliases defined)")
    return "\n".join(lines)


def _switch_active_profile_model(alias: str, path: Path) -> tuple[str, str, str, str | None] | None:
    """Resolve and persist a model selection on the active provider profile.

    Returns (provider, model_id, base_url, suggestion) or None if no active
    profile is configured.
    """
    if not alias or alias in _MODEL_SPECIAL_KEYWORDS:
        return None
    from safecode.llm.provider_profiles import get_active_profile, save_profile
    profile = get_active_profile(path)
    if profile is None:
        return None
    if ":" in alias:
        prefix, _, _model_part = alias.partition(":")
        if prefix and prefix != profile.name:
            raise ValueError(
                f"Model scope '{prefix}' does not match active provider '{profile.name}'. "
                f"Run `sac provider use {prefix}` first, or use an unscoped model ID."
            )
    resolved, suggestion = profile.resolve_model(alias)
    save_profile(profile.model_copy(update={"default_model": resolved}), path)
    return profile.name, resolved, profile.base_url, suggestion


def apply_model_override_env(model: str, path: Path | None = None) -> tuple[str | None, str, str | None]:
    """Apply a one-shot model override through process env vars.

    This is intentionally session-only: it never writes user config. Returns
    (provider_or_None, resolved_model, suggestion_or_None).
    """
    model = model.strip()
    if not model:
        raise ValueError("model override must be non-empty")
    user_path = path or _user_config_path()

    from safecode.llm.provider_profiles import _PROVIDER_PRESETS, get_active_profile
    profile = get_active_profile(user_path)

    if ":" in model:
        provider, _, alias = model.partition(":")
        if not provider or not alias:
            raise ValueError(f"Invalid model override: {model!r}")
        preset = _PROVIDER_PRESETS.get(provider, {})
        aliases = dict(preset.get("model_aliases", {}))
        resolved = aliases.get(alias, alias)
        os.environ["SAFECODE_LLM_PROVIDER"] = provider
        os.environ["SAFECODE_LLM_MODEL"] = resolved
        return provider, resolved, None

    if profile is not None:
        resolved, suggestion = profile.resolve_model(model)
        os.environ["SAFECODE_LLM_PROVIDER"] = profile.name
        os.environ["SAFECODE_LLM_MODEL"] = resolved
        return profile.name, resolved, suggestion

    os.environ["SAFECODE_LLM_MODEL"] = model
    return None, model, None


def _render_model_session_status(config: SafeCodeConfig, path: Path) -> str:
    """Show session overrides vs persisted model config."""
    import os
    session_provider = os.getenv("SAFECODE_LLM_PROVIDER")
    session_model = os.getenv("SAFECODE_LLM_MODEL")
    key_state = "configured" if config.llm.api_key else "not configured"
    lines = [
        "[bold]Model Status[/bold]",
        "",
        f"  Persisted provider : {config.llm.provider}",
        f"  Persisted model    : {config.llm.model}",
        f"  Persisted base URL : {config.llm.base_url}",
        f"  API key: {key_state}",
    ]
    if session_provider and session_model:
        lines.append("")
        lines.append(f"  [bold]Session override:[/bold]")
        lines.append(f"  Session provider   : {session_provider}")
        lines.append(f"  Session model      : {session_model}")
    else:
        lines.append("")
        lines.append("  [dim]No session override active.[/dim]")
    return redact_secrets("\n".join(lines))


def register(app: typer.Typer) -> None:
    """Register the user-facing `sac model` command."""

    @app.command("model", hidden=True)
    def model_command(
        model: str = typer.Argument(
            "",
            help=(
                "Model alias or name. "
                "'status' shows session vs persisted. "
                "'list' shows available aliases for the active provider. "
                "Omit to show current model config."
            ),
        ),
        save: bool = typer.Option(False, "--save", help="Persist the model selection to user config (default: session-only)."),
        provider: str = typer.Option("", "--provider", "-p", help="Provider: mock, openai, openai-compatible, anthropic, deepseek."),
        api_key: str = typer.Option("", "--api-key", help="Persist an API key in the trusted user config."),
        base_url: str = typer.Option("", "--base-url", help="Override the provider endpoint/base URL."),
        network: bool = typer.Option(False, "--network", help="Enable user-level network permission."),
        no_network: bool = typer.Option(False, "--no-network", help="Disable user-level network permission."),
    ) -> None:
        """Show or switch the model configuration.

        Model switching is session-only by default (v4.15.1+):
          sac model flash       -- session-only switch to deepseek-v4-flash
          sac model --save pro  -- persist deepseek-v4-pro to user config
          sac model status      -- show session vs persisted model
          sac model list        -- show available aliases

        Original explicit form (still requires --save for persistence):
          sac model gpt-4.1-mini --provider openai --api-key sk-... --save
        """
        import os
        path = _user_config_path()

        # Legacy persist mode check
        if os.getenv("SAFECODE_LEGACY_MODEL_PERSIST") == "1":
            save = True
            console.print("[yellow]SAFECODE_LEGACY_MODEL_PERSIST=1 is deprecated. "
                          "Use --save to persist model selections.[/yellow]")

        # No argument: show current status
        if not model:
            console.print(_render_model_session_status(SafeCodeConfig.load(Path.cwd()), path))
            return

        # "status" keyword: show session vs persisted
        if model == "status":
            console.print(_render_model_session_status(SafeCodeConfig.load(Path.cwd()), path))
            return

        # "list" keyword: show available aliases for active provider
        if model == "list":
            console.print(_render_model_list(Path.cwd(), path))
            return

        # Session-only path (no --save, no explicit config write)
        if not save and not provider and not api_key and not base_url:
            try:
                provider_name, resolved, suggestion = apply_model_override_env(model, path)
            except ValueError as exc:
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(code=1) from exc
            if suggestion:
                console.print(f"[yellow]{suggestion}[/yellow]")
            console.print(f"[green]Session model override: {resolved}[/green]")
            console.print(f"  Provider: {provider_name or '(env override)'}")
            console.print("  [dim]Session-only — not persisted. Use --save to write config.[/dim]")
            return

        # Persist path: --save or explicit --provider/--api-key/--base-url
        if not provider and not api_key and not base_url:
            try:
                switched = _switch_active_profile_model(model, path)
            except ValueError as exc:
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(code=1) from exc
            if switched is not None:
                selected_provider, resolved, active_base_url, suggestion = switched
                if suggestion:
                    console.print(f"[yellow]{suggestion}[/yellow]")
                network_setting = True if network else False if no_network else None
                try:
                    written = write_user_model_config(
                        provider=selected_provider,
                        model=resolved,
                        base_url=active_base_url or None,
                        api_key=None,
                        enable_user_network=network_setting,
                    )
                except ValueError as exc:
                    console.print(f"[red]{exc}[/red]")
                    raise typer.Exit(code=1) from exc
                console.print(
                    "\n".join([
                        f"[green]Model config saved globally: {written}[/green]",
                        f"Provider: {selected_provider}",
                        f"Model: {resolved}",
                        f"(resolved from alias '{model}')",
                    ])
                )
                return

        # Original explicit form: sac model <name> --provider <p> ... --save
        current = SafeCodeConfig.load(Path.cwd())
        selected_provider = provider or current.llm.provider
        network_setting = True if network else False if no_network else None
        try:
            written = write_user_model_config(
                provider=selected_provider,
                model=model,
                base_url=base_url or None,
                api_key=api_key if api_key else None,
                enable_user_network=network_setting,
            )
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

        console.print(
            "\n".join(
                [
                    f"Model config saved: {written}",
                    f"Provider: {selected_provider}",
                    f"Model: {model}",
                    f"API key: {'configured' if api_key else 'unchanged'}",
                ]
            )
        )
