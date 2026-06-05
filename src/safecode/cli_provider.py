"""EXPERIMENTAL: sac provider — provider profile management (v4.14.0).

Manage provider profiles in the trusted user config.  Profiles store base_url,
default model, model aliases, and network allowlist.  API keys are stored in the
user config or supplied via environment variables; they are NEVER written to
project-local config.

Supported commands:
  sac provider add deepseek   -- configure provider with preset defaults
  sac provider list           -- list configured providers
  sac provider status         -- show current effective provider status
  sac provider use <name>     -- set the active provider
  sac provider rm <name>      -- remove a provider profile

All surfaces in this module are EXPERIMENTAL and carry no stable contract.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from safecode.cli_shared import console
from safecode.core.diagnostic import DiagnosticStatus
from safecode.llm.provider_profiles import (
    SUPPORTED_PROVIDERS,
    _PROVIDER_PRESETS,
    get_active_profile,
    get_active_profile_name,
    load_profiles,
    make_deepseek_profile,
    remove_profile,
    save_profile,
    set_active_provider,
)

provider_app = typer.Typer(
    name="provider",
    help="[EXPERIMENTAL] Manage provider profiles (v4.14.0).",
    no_args_is_help=True,
)


@provider_app.command("add")
def provider_add(
    name: str = typer.Argument(..., help="Provider name to configure: deepseek"),
    api_key: str = typer.Option("", "--api-key", help="API key (prefer env var; requires --store for persistence)."),
    store: str = typer.Option("", "--store", help="Storage backend for the API key: user-config | keychain."),
    default_model: str = typer.Option("", "--default-model", help="Default model alias or ID (e.g. flash, pro)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """[EXPERIMENTAL] Configure a provider profile with preset defaults.

    Example:
      sac provider add deepseek

    For DeepSeek: sets base_url, model aliases (flash/pro), and network allowlist.
    In TTY mode, prompts for API key if --api-key is not supplied.
    API keys default to env var usage. Pass --store user-config or --store keychain
    to persist a key to disk or system keychain.

    Never writes credentials to project-local config.
    """
    name = name.strip().lower()
    if name not in _PROVIDER_PRESETS:
        from safecode.llm.provider_profiles import _fuzzy_match_provider
        supported = ", ".join(sorted(_PROVIDER_PRESETS))
        fuzzy = _fuzzy_match_provider(name)
        hint = f"\nDid you mean '{fuzzy}'?" if fuzzy else ""
        console.print(f"[red]Provider '{name}' has no built-in preset. Supported: {supported}[/red]{hint}")
        raise typer.Exit(code=1)

    # Validate --store
    store_mode = store.strip().lower()
    if store_mode and store_mode not in ("user-config", "keychain"):
        console.print("[red]--store must be 'user-config' or 'keychain'[/red]")
        raise typer.Exit(code=1)

    # Require --store when --api-key is passed with a literal value
    if api_key.strip() and not store_mode:
        console.print(
            "[red]--api-key requires --store to specify where the key should be persisted.[/red]\n"
            "[dim]Use --store user-config to save in ~/.safecode/config.toml (0o600), or\n"
            "--store keychain to save in the system keyring (macOS Keychain / Linux Secret Service).[/dim]"
        )
        raise typer.Exit(code=1)

    preset = _PROVIDER_PRESETS[name]
    is_tty = sys.stdin.isatty() and sys.stdout.isatty()

    # Resolve API key: --api-key > env var > TTY prompt > none
    resolved_key: str | None = None
    env_var = preset.get("api_key_env", "")
    import os
    if api_key.strip():
        resolved_key = api_key.strip()
    elif env_var and os.getenv(env_var):
        resolved_key = None  # will be used at runtime; don't persist env var value
        console.print(f"[dim]Using {env_var} from environment (not persisted).[/dim]")
    elif is_tty and not yes:
        console.print(f"[yellow]{name.title()} API key not found in environment ({env_var}).[/yellow]")
        try:
            raw = typer.prompt(
                f"Enter API key (or press Enter to skip — you can set {env_var} later)",
                default="",
                hide_input=True,
            )
        except (EOFError, KeyboardInterrupt):
            raw = ""
        resolved_key = raw.strip() or None
        if resolved_key and not store_mode:
            console.print("[dim]Tip: use --store user-config or --store keychain to persist the key.[/dim]")
    else:
        console.print(f"[dim]No API key supplied. Set {env_var} before running sac.[/dim]")

    # If keychain storage requested, store the key there
    keychain_stored = False
    if resolved_key and store_mode == "keychain":
        from safecode.security.keychain import store_api_key
        keychain_stored = store_api_key(name, resolved_key)
        if keychain_stored:
            console.print(f"[green]API key stored in system keychain for '{name}'.[/green]")
            resolved_key = None  # Don't also write to user config
        else:
            console.print("[yellow]Keychain unavailable; falling back to user config.[/yellow]")
            store_mode = "user-config"

    # Build profile from preset
    if name == "deepseek":
        profile = make_deepseek_profile(api_key=resolved_key)
    else:
        from safecode.llm.provider_profiles import ProviderProfile
        profile = ProviderProfile(
            name=name,
            base_url=str(preset.get("base_url", "")),
            api_key=resolved_key,
            default_model=str(preset.get("default_model", "")),
            model_aliases=dict(preset.get("model_aliases", {})),
            network_allowlist=list(preset.get("network_allowlist", [])),
        )

    # Override default model if supplied
    if default_model.strip():
        resolved_dm, _ = profile.resolve_model(default_model.strip())
        profile = profile.model_copy(update={"default_model": resolved_dm})

    # Write profile and set as active
    from safecode.config import _user_config_path
    path = _user_config_path().expanduser()
    save_profile(profile, path)
    set_active_provider(name, path)

    # Also update user-level network allowlist so the provider host is allowed.
    _ensure_network_allowlist(profile.network_allowlist, path)

    console.print(f"[green]Provider '{name}' configured.[/green]")
    console.print(f"  Config: {path}")
    console.print(f"  Base URL: {profile.base_url}")
    console.print(f"  Default model: {profile.default_model}")
    if profile.model_aliases:
        alias_str = ", ".join(f"{k} -> {v}" for k, v in sorted(profile.model_aliases.items()))
        console.print(f"  Aliases: {alias_str}")
    console.print(f"  Network allowlist: {profile.network_allowlist}")
    if keychain_stored:
        console.print("  API key: stored in system keychain")
    elif resolved_key:
        console.print("  API key: stored in user config")
    else:
        console.print(f"  API key: {'env:' + env_var if env_var else 'not set'}")
    console.print("")
    console.print("[dim]Next: sac model flash   or   sac model pro[/dim]")


@provider_app.command("list")
def provider_list() -> None:
    """[EXPERIMENTAL] List configured provider profiles."""
    from safecode.config import _user_config_path
    path = _user_config_path().expanduser()
    profiles = load_profiles(path)
    active = get_active_profile_name(path)
    if not profiles:
        console.print("No provider profiles configured.")
        console.print("Run: sac provider add deepseek")
        return
    for name, profile in sorted(profiles.items()):
        marker = " (active)" if name == active else ""
        console.print(f"  {name}{marker}")
        console.print(f"    base_url: {profile.base_url}")
        console.print(f"    default_model: {profile.default_model}")
        console.print(f"    api_key: {profile.api_key_source()}")


@provider_app.command("status")
def provider_status(
    live: bool = typer.Option(False, "--live", help="Attempt a lightweight connectivity ping to the provider (opt-in)."),
) -> None:
    """[EXPERIMENTAL] Show current effective provider and model status."""
    from safecode.config import SafeCodeConfig, _read_toml, _user_config_path
    path = _user_config_path().expanduser()
    active_name = get_active_profile_name(path)
    active_profile = get_active_profile(path)
    config = SafeCodeConfig.load(Path.cwd())
    user_data = _read_toml(path)
    project_data = _read_toml(Path.cwd() / ".sac" / "config.toml")
    user_sandbox = user_data.get("sandbox", {}) if isinstance(user_data.get("sandbox", {}), dict) else {}
    project_sandbox = project_data.get("sandbox", {}) if isinstance(project_data.get("sandbox", {}), dict) else {}
    user_network_enabled = bool(user_sandbox.get("network_enabled", False))
    project_network_enabled = bool(project_sandbox.get("network_enabled", False))
    user_allowlist = list(user_sandbox.get("network_allowlist", []))
    project_allowlist = list(project_sandbox.get("network_allowlist", []))

    # Determine top-line verdict
    ready = (
        active_name is not None
        and active_profile is not None
        and active_profile.api_key_source() != "missing"
        and (config.sandbox.network_enabled or config.llm.provider == "mock")
    )
    if ready:
        verdict = "[bold green]READY[/bold green]"
        verdict_line = f"  {active_name} / {config.llm.model} / {config.llm.base_url}"
    else:
        verdict = "[bold red]BROKEN[/bold red]"
        issues: list[str] = []
        if active_name is None:
            issues.append("no provider configured")
        elif active_profile and active_profile.api_key_source() == "missing":
            issues.append("API key missing")
        if not config.sandbox.network_enabled and config.llm.provider != "mock":
            issues.append("network disabled")
        verdict_line = " — ".join(issues) if issues else "check details below"

    lines = [
        f"[bold]Provider Status[/bold] [dim](EXPERIMENTAL)[/dim]",
        f"  Verdict: {verdict}  {verdict_line}",
        "",
        "[bold]Details:[/bold]",
        f"  Active provider profile : {active_name or '(none)'}",
        f"  Effective provider      : {config.llm.provider}",
        f"  Effective model         : {config.llm.model}",
        f"  Base URL                : {config.llm.base_url}",
    ]

    if active_profile:
        source = active_profile.api_key_source()
        lines.append(f"  Credential source       : {source}")
        if active_profile.model_aliases:
            alias_str = ", ".join(f"{k} -> {v}" for k, v in sorted(active_profile.model_aliases.items()))
            lines.append(f"  Model aliases           : {alias_str}")
    else:
        import os
        env_provider = os.getenv("SAFECODE_LLM_PROVIDER")
        if env_provider:
            lines.append(f"  Credential source       : env:SAFECODE_LLM_PROVIDER")
        elif config.llm.api_key:
            lines.append(f"  Credential source       : user-config [llm]")
        else:
            lines.append(f"  Credential source       : missing")

    lines.append(f"  User network enabled    : {user_network_enabled}")
    lines.append(f"  Project network enabled : {project_network_enabled}")
    lines.append(f"  Effective network       : {config.sandbox.network_enabled}")
    lines.append(f"  User network allowlist  : {user_allowlist or '[]'}")
    lines.append(f"  Project network allowlist: {project_allowlist or '[]'}")

    # Next step guidance
    lines.append("")
    if active_name is None:
        lines.append("[yellow]  -> Run: sac provider add deepseek[/yellow]")
    elif active_profile and active_profile.api_key_source() == "missing":
        preset = _PROVIDER_PRESETS.get(active_name, {})
        env_var = preset.get("api_key_env", "")
        if env_var:
            lines.append(f"[yellow]  -> Set {env_var} or run: sac provider add {active_name} --api-key <key>[/yellow]")
    if active_name and not user_network_enabled:
        lines.append(f"[yellow]  -> Enable user network: sac provider add {active_name} --yes[/yellow]")
    if active_name and not project_network_enabled:
        lines.append("[yellow]  -> Enable project network: sac setup --yes --network[/yellow]")

    if live:
        lines.append("")
        lines.append("[bold]Live Connectivity:[/bold]")
        from safecode.doctor import Doctor
        ping = Doctor._live_provider_ping(config.llm.base_url)
        status_label = {DiagnosticStatus.PASS: "[green]PASS[/green]",
                        DiagnosticStatus.FAIL: "[red]FAIL[/red]",
                        DiagnosticStatus.SKIP: "[dim]SKIP[/dim]",
                        DiagnosticStatus.WARN: "[yellow]WARN[/yellow]"}.get(ping.status, ping.status.value)
        lines.append(f"  {status_label}  {ping.message}")

    for line in lines:
        console.print(line)


@provider_app.command("use")
def provider_use(
    name: str = typer.Argument(..., help="Provider name to activate."),
) -> None:
    """[EXPERIMENTAL] Set the active provider profile."""
    name = name.strip().lower()
    from safecode.config import _user_config_path
    path = _user_config_path().expanduser()
    profiles = load_profiles(path)
    if name not in profiles:
        console.print(f"[red]Provider '{name}' not configured.[/red]")
        console.print(f"Run: sac provider add {name}")
        raise typer.Exit(code=1)
    set_active_provider(name, path)
    console.print(f"Active provider set to '{name}'.")
    profile = profiles[name]
    console.print(f"Default model: {profile.default_model}")


@provider_app.command("rm")
def provider_rm(
    name: str = typer.Argument(..., help="Provider name to remove."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """[EXPERIMENTAL] Remove a provider profile."""
    name = name.strip().lower()
    from safecode.config import _user_config_path
    path = _user_config_path().expanduser()
    profiles = load_profiles(path)
    if name not in profiles:
        console.print(f"[yellow]Provider '{name}' not found.[/yellow]")
        return
    if not yes:
        confirmed = typer.confirm(f"Remove provider profile '{name}'?", default=False)
        if not confirmed:
            console.print("Cancelled.")
            return
    # Also clean up keychain entry if present.
    from safecode.security.keychain import delete_api_key
    delete_api_key(name)

    removed = remove_profile(name, path)
    if removed:
        console.print(f"Provider profile '{name}' removed.")
    else:
        console.print(f"[yellow]Provider '{name}' not found.[/yellow]")
    console.print("[dim]Tip: if this was the active profile, run 'sac provider use <name>' to switch.[/dim]")


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _ensure_network_allowlist(hosts: list[str], config_path: Path) -> None:
    """Add provider hosts to the user-level sandbox network allowlist."""
    if not hosts:
        return
    import tomllib as _tomllib
    data: dict = {}
    if config_path.exists():
        data = _tomllib.loads(config_path.read_text(encoding="utf-8"))
    sandbox = dict(data.get("sandbox", {}))
    existing = list(sandbox.get("network_allowlist", []))
    changed = False
    if sandbox.get("network_enabled") is not True:
        sandbox["network_enabled"] = True
        changed = True
    for host in hosts:
        if host not in existing:
            existing.append(host)
            changed = True
    if changed:
        sandbox["network_allowlist"] = sorted(existing)
        data["sandbox"] = sandbox
        from safecode.llm.provider_profiles import _render_user_toml
        config_path.write_text(_render_user_toml(data), encoding="utf-8")
