"""EXPERIMENTAL: sac init — guided first-run provider and policy setup (v4.15.0).

Replaces sac setup --wizard and sac provider add as the recommended entry point.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import typer

from safecode.cli_shared import console
from safecode.llm.provider_profiles import (
    _PROVIDER_PRESETS,
    get_active_profile,
    load_profiles,
    make_deepseek_profile,
    remove_profile,
    save_profile,
    set_active_provider,
)


def _init_live_connectivity_check(provider: str, api_key: str, console_obj: object) -> None:
    """B15 fix: lightweight live API ping after sac init for non-mock providers.

    Uses the same Doctor ping methods as sac doctor --live. On failure prints
    a yellow warning instead of exiting — setup is already written; the user
    just needs to know the credentials may be invalid.
    """
    try:
        from safecode.doctor import Doctor
        from safecode.core.diagnostic import DiagnosticStatus

        console_obj.print("")
        console_obj.print("[dim]Checking provider connectivity...[/dim]")

        if provider == "anthropic":
            diag = Doctor._live_anthropic_ping(api_key)
        else:
            # For OpenAI-compatible and DeepSeek: use base URL from preset.
            from safecode.llm.provider_profiles import _PROVIDER_PRESETS
            preset = _PROVIDER_PRESETS.get(provider, {})
            base_url = str(preset.get("base_url", ""))
            diag = Doctor._live_provider_ping(base_url)

        if diag.status == DiagnosticStatus.PASS:
            console_obj.print("[green]Provider API reachable.[/green]")
        elif diag.status == DiagnosticStatus.SKIP:
            pass  # No key or offline — silently skip.
        else:
            console_obj.print(
                "[yellow]Warning: could not reach the provider API. "
                "Credentials may be missing or invalid.[/yellow]"
            )
            console_obj.print("[dim]  Run 'sac doctor --live' after setup to verify connectivity.[/dim]")
    except Exception:
        # Never let a ping failure block the init completion.
        pass


def _detect_api_key(provider: str) -> tuple[str, bool]:
    """Return (env_var_name, is_set) for the provider's API key env var."""
    if provider == "deepseek":
        return "DEEPSEEK_API_KEY", bool(os.getenv("DEEPSEEK_API_KEY"))
    elif provider in ("openai", "openai-compatible"):
        return "OPENAI_API_KEY", bool(os.getenv("OPENAI_API_KEY"))
    elif provider == "anthropic":
        return "ANTHROPIC_API_KEY", bool(os.getenv("ANTHROPIC_API_KEY"))
    else:
        return "API_KEY", False


def run_init(
    project_root: Path,
    *,
    is_tty: bool = True,
    provider: str | None = None,
    api_key: str | None = None,
    default_model: str | None = None,
    policy: str | None = None,
    yes: bool = False,
) -> int:
    """Core init logic. Returns exit code."""
    from safecode.config import _user_config_path, _read_toml
    user_config_path = _user_config_path().expanduser()

    # Validate explicit flags first (both TTY and non-TTY).
    _POLICY_PRESETS = ["strict", "balanced", "experimental"]
    if provider:
        provider = provider.strip().lower()
        if provider not in _PROVIDER_PRESETS and provider != "mock":
            console.print(f"[red]Provider '{provider}' has no built-in preset. Supported: {', '.join(sorted(_PROVIDER_PRESETS))}, mock[/red]")
            return 1
    if policy:
        policy = policy.strip().lower()
        if policy not in _POLICY_PRESETS:
            console.print(f"[red]Unknown policy: {policy}. Must be one of: {', '.join(_POLICY_PRESETS)}[/red]")
            return 1

    # Non-TTY: print a static template
    if not is_tty:
        console.print("[bold]SafeCode Agent — Initial Setup[/bold]")
        console.print("")
        console.print("Run interactively (TTY) to use the guided wizard, or use flags:")
        console.print("  sac init --provider deepseek --api-key sk-... --policy balanced")
        console.print("")
        console.print("Equivalent manual steps:")
        console.print("  sac provider add deepseek --api-key <key>")
        console.print("  sac setup --policy balanced --network")
        console.print("")
        console.print("[dim]Run 'sac init --help' for all flags.[/dim]")
        return 0

    # ── TTY interactive wizard ────────────────────────────────────────
    console.print("[bold]SafeCode Agent — Initial Setup[/bold]")
    console.print("")
    console.print("Let's configure a provider and safety policy.")
    console.print("Press Ctrl-C at any time to cancel.")
    console.print("")

    # 1. Provider choice
    if provider is not None:
        pass  # Already validated above
    else:
        provider_names = sorted(_PROVIDER_PRESETS)
        console.print("[bold]Which provider?[/bold]")
        for i, name in enumerate(provider_names, 1):
            preset = _PROVIDER_PRESETS[name]
            desc = preset.get("default_model", "")
            console.print(f"  {i}. {name:12s} {desc}")
        console.print(f"  {len(provider_names) + 1}. mock        deterministic, no network (tests)")

        default_choice = "1"
        try:
            choice = typer.prompt(
                "Choose provider",
                default=default_choice,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/yellow]")
            return 0

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(provider_names):
                provider = provider_names[idx]
            elif idx == len(provider_names):
                provider = "mock"
            else:
                console.print(f"[red]Invalid choice: {choice}[/red]")
                return 1
        except ValueError:
            if choice.lower() in _PROVIDER_PRESETS or choice.lower() == "mock":
                provider = choice.lower()
            else:
                console.print(f"[red]Unknown provider: {choice}[/red]")
                return 1

    if provider not in _PROVIDER_PRESETS and provider != "mock":
        console.print(f"[red]Provider '{provider}' has no built-in preset.[/red]")
        return 1

    # 2. API key
    if provider == "mock":
        key_configured = False
        resolved_key: str | None = None
        console.print("[dim]Mock provider selected — no API key needed.[/dim]")
    elif api_key:
        resolved_key = api_key.strip()
        key_configured = True
    else:
        env_var, env_set = _detect_api_key(provider)
        if env_set:
            console.print(f"[green]Detected {env_var} in environment.[/green]")
            console.print("[dim]Using env var (not persisted to config).[/dim]")
            resolved_key = None
            key_configured = True
        else:
            console.print(f"[yellow]No API key found in environment ({env_var}).[/yellow]")
            console.print("")
            console.print("Options:")
            console.print(f"  1. Paste key (stored in user config at 0o600)")
            console.print(f"  2. Set {env_var} env var and re-run")
            console.print(f"  3. Skip — I'll configure it later")

            try:
                choice = typer.prompt(
                    "Choose option",
                    default="1",
                ).strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Cancelled.[/yellow]")
                return 0

            if choice == "1":
                try:
                    raw = typer.prompt(
                        f"Paste API key for {provider}",
                        default="",
                        hide_input=True,
                    )
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[yellow]Cancelled.[/yellow]")
                    return 0
                resolved_key = raw.strip() or None
                key_configured = resolved_key is not None
            elif choice == "2":
                console.print(f"Set {env_var} in your shell profile, then re-run: sac init")
                return 0
            else:
                resolved_key = None
                key_configured = False
                console.print(f"[dim]Skipped. Set {env_var} before running sac.[/dim]")

    # 3. Default model
    if provider == "mock":
        resolved_model = "gpt-4.1-mini"
    elif default_model:
        resolved_model = default_model.strip()
    else:
        preset = _PROVIDER_PRESETS.get(provider, {})
        preset_default = str(preset.get("default_model", ""))
        aliases = dict(preset.get("model_aliases", {}))
        if aliases:
            console.print("")
            console.print("[bold]Available model aliases:[/bold]")
            alias_list = sorted(aliases.items())
            for i, (alias, model_id) in enumerate(alias_list, 1):
                marker = " (recommended)" if model_id == preset_default else ""
                console.print(f"  {i}. {alias:12s} -> {model_id}{marker}")
            console.print(f"  {len(alias_list) + 1}. Custom model ID")

            try:
                choice = typer.prompt(
                    "Choose default model",
                    default="1",
                ).strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Cancelled.[/yellow]")
                return 0

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(alias_list):
                    resolved_model = alias_list[idx][1]
                else:
                    resolved_model = typer.prompt("Enter model ID").strip()
            except ValueError:
                resolved_model = choice
        else:
            resolved_model = preset_default or typer.prompt(
                "Model name",
                default="gpt-4.1-mini",
            ).strip()

    # 4. Policy preset
    if policy is not None:
        pass  # Already validated above
    else:
        console.print("")
        console.print("[bold]Safety policy preset:[/bold]")
        console.print("  1. balanced     — daily driver (recommended)")
        console.print("  2. strict       — maximum safety, blocks medium-risk commands")
        console.print("  3. experimental — relaxed, for power users")
        try:
            choice = typer.prompt(
                "Choose policy",
                default="1",
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/yellow]")
            return 0

        policy_map = {"1": "balanced", "2": "strict", "3": "experimental"}
        policy = policy_map.get(choice, "balanced")
        if policy not in _POLICY_PRESETS:
            console.print(f"[red]Invalid policy choice: {choice}[/red]")
            return 1

    # 5. Write configuration
    console.print("")
    console.print("[bold]Summary:[/bold]")
    console.print(f"  Provider: {provider}")
    console.print(f"  Model: {resolved_model}")
    console.print(f"  Policy: {policy}")
    console.print(f"  API key: {'configured' if key_configured and resolved_key else 'env var' if key_configured else 'not configured'}")
    console.print(f"  Config path: {user_config_path}")

    if not yes:
        try:
            confirmed = typer.confirm("Write configuration?", default=True)
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/yellow]")
            return 0
        if not confirmed:
            console.print("[yellow]Cancelled.[/yellow]")
            return 0

    # Write provider profile
    if provider != "mock":
        if provider == "deepseek":
            profile = make_deepseek_profile(api_key=resolved_key)
        else:
            from safecode.llm.provider_profiles import ProviderProfile
            preset_data = _PROVIDER_PRESETS[provider]
            profile = ProviderProfile(
                name=provider,
                base_url=str(preset_data.get("base_url", "")),
                api_key=resolved_key,
                default_model=resolved_model,
                model_aliases=dict(preset_data.get("model_aliases", {})),
                network_allowlist=list(preset_data.get("network_allowlist", [])),
            )

        save_profile(profile, user_config_path)
        set_active_provider(provider, user_config_path)

        # Ensure network allowlist includes provider host
        from safecode.cli_provider import _ensure_network_allowlist
        _ensure_network_allowlist(profile.network_allowlist, user_config_path)

    # Write policy + project config
    from safecode.setup import write_setup
    setup_result = write_setup(
        project_root,
        provider=provider,
        model=resolved_model,
        policy=policy,
        force=True,
    )

    console.print("")
    console.print(f"[green]Configuration written.[/green]")
    if setup_result:
        console.print(f"  Project config: {setup_result.config_path}")
    console.print(f"  User config: {user_config_path}")

    # B15 fix: live connectivity check when using a real provider with network.
    network_enabled = provider != "mock"  # non-mock providers always need network
    if network_enabled and resolved_key:
        _init_live_connectivity_check(provider, resolved_key, console)

    console.print("")
    console.print("[bold]Ready![/bold] Try these next:")
    console.print('  sac ask "What does this project do?"')
    console.print('  sac edit "Add a docstring to main()"')
    console.print("  sac fix")

    return 0


def register(app: typer.Typer) -> None:
    """Register the sac init command."""

    @app.command("init")
    def init_command(
        provider: str = typer.Option("", "--provider", help="Provider: deepseek, openai, anthropic, mock."),
        api_key: str = typer.Option("", "--api-key", help="API key (prefer env var)."),
        default_model: str = typer.Option("", "--default-model", help="Default model alias or ID."),
        policy: str = typer.Option("", "--policy", help="Safety preset: strict, balanced, experimental."),
        yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts."),
    ) -> None:
        """[EXPERIMENTAL] Guided first-run: configure provider, model, and safety policy.

        In TTY mode, walks through an interactive wizard.
        In non-TTY mode, prints a static flag template.

        This is the recommended first command after installation.
        """
        is_tty = sys.stdin.isatty() and sys.stdout.isatty()
        code = run_init(
            Path.cwd(),
            is_tty=is_tty,
            provider=provider or None,
            api_key=api_key or None,
            default_model=default_model or None,
            policy=policy or None,
            yes=yes,
        )
        raise typer.Exit(code=code)
