"""sac profile command group (v4.2, EXPERIMENTAL).

Subcommands:
  detect  — detect and persist .sac/project_profile.json
  show    — display the current profile
  set     — set a user override for one kind
  clear   — clear a user override for one kind
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Optional

import typer

from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json
from safecode.project.profile import (
    ProfileCommand,
    ProjectProfile,
    _SHELL_METACHAR,
    _VALID_KINDS,
    _has_metachar,
    apply_user_override,
    clear_user_override,
    detect_profile,
    load_profile,
    save_profile,
)

profile_app = typer.Typer(
    name="profile",
    help="[EXPERIMENTAL] Manage project command profile (test/lint/typecheck/build). (v4.2+)",
    no_args_is_help=True,
)

_KIND_HELP = "Kind: test, lint, typecheck, or build."


def _cmd_to_dict(cmd: ProfileCommand | None) -> dict:
    if cmd is None:
        return {"source": "none", "command": None, "stack": None, "missing_dependency": False}
    return {
        "command": list(cmd.command),
        "stack": cmd.stack,
        "source": cmd.source,
        "missing_dependency": cmd.missing_dependency,
    }


def _profile_to_data(profile: ProjectProfile) -> dict:
    return {
        "payload_version": profile.payload_version,
        "test": _cmd_to_dict(profile.test),
        "lint": _cmd_to_dict(profile.lint),
        "typecheck": _cmd_to_dict(profile.typecheck),
        "build": _cmd_to_dict(profile.build),
        "user_overrides": sorted(profile.user_overrides),
    }


def _print_profile_human(profile: ProjectProfile) -> None:
    """Render the profile in human-readable form."""
    console.print("[bold]Project Command Profile[/bold] [dim](EXPERIMENTAL)[/dim]")
    for kind in ("test", "lint", "typecheck", "build"):
        cmd: ProfileCommand | None = getattr(profile, kind)
        if cmd is None:
            console.print(f"  [dim]{kind:12}[/dim] (not detected)")
        else:
            argv_str = " ".join(cmd.command)
            flags = []
            if cmd.source == "user":
                flags.append("user override")
            if cmd.missing_dependency:
                flags.append("tool missing")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            console.print(f"  [cyan]{kind:12}[/cyan] {argv_str}{flag_str}")
    if profile.user_overrides:
        console.print(f"  [dim]user_overrides: {sorted(profile.user_overrides)}[/dim]")


@profile_app.command("detect")
def profile_detect(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Detect project command profile and save to .sac/project_profile.json."""
    project_root = Path.cwd()
    profile = detect_profile(project_root)
    save_profile(project_root, profile)

    if json_output:
        print(render_json(CLIJSONResponse(
            command="profile detect",
            status="success",
            data=_profile_to_data(profile),
        )))
        return

    console.print("[green]Profile detected and saved.[/green]")
    _print_profile_human(profile)


@profile_app.command("show")
def profile_show(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Show the current project command profile."""
    project_root = Path.cwd()
    profile = load_profile(project_root)

    if profile is None:
        msg = "No profile found. Run 'sac profile detect' first."
        if json_output:
            print(render_json(CLIJSONResponse(
                command="profile show",
                status="error",
                error=msg,
            )))
        else:
            console.print(f"[yellow]{msg}[/yellow]")
        raise typer.Exit(code=1)

    if json_output:
        print(render_json(CLIJSONResponse(
            command="profile show",
            status="success",
            data=_profile_to_data(profile),
        )))
        return

    _print_profile_human(profile)


@profile_app.command("set")
def profile_set(
    kind: str = typer.Argument(help=_KIND_HELP),
    command: str = typer.Argument(help='Command string (e.g. "pytest -q"). Parsed with shlex.split.'),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Set a user override command for a profile kind."""
    project_root = Path.cwd()

    if kind not in _VALID_KINDS:
        msg = f"Unknown kind: {kind!r}. Must be one of: {sorted(_VALID_KINDS)}"
        if json_output:
            print(render_json(CLIJSONResponse(command="profile set", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    # Reject shell metacharacters before shlex
    if _has_metachar(command):
        bad = [c for c in command if c in _SHELL_METACHAR]
        msg = f"Command contains shell metacharacters: {bad!r}. Use argv tuple form."
        if json_output:
            print(render_json(CLIJSONResponse(command="profile set", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    try:
        parsed = shlex.split(command)
    except ValueError as exc:
        msg = f"Could not parse command: {exc}"
        if json_output:
            print(render_json(CLIJSONResponse(command="profile set", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1) from exc

    if not parsed:
        msg = "Command must not be empty."
        if json_output:
            print(render_json(CLIJSONResponse(command="profile set", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    argv = tuple(parsed)
    updated = apply_user_override(project_root, kind, argv)

    if json_output:
        print(render_json(CLIJSONResponse(
            command="profile set",
            status="success",
            data={"kind": kind, "command": list(argv), **_profile_to_data(updated)},
        )))
        return

    console.print(f"[green]User override set for '{kind}':[/green] {' '.join(argv)}")


@profile_app.command("clear")
def profile_clear(
    kind: str = typer.Argument(help=_KIND_HELP),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Clear a user override for a profile kind (restores detected command)."""
    project_root = Path.cwd()

    if kind not in _VALID_KINDS:
        msg = f"Unknown kind: {kind!r}. Must be one of: {sorted(_VALID_KINDS)}"
        if json_output:
            print(render_json(CLIJSONResponse(command="profile clear", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    updated = clear_user_override(project_root, kind)

    if json_output:
        print(render_json(CLIJSONResponse(
            command="profile clear",
            status="success",
            data={"kind": kind, **_profile_to_data(updated)},
        )))
        return

    console.print(f"[green]User override cleared for '{kind}'.[/green]")
    cmd = getattr(updated, kind)
    if cmd:
        console.print(f"  Restored: {' '.join(cmd.command)}")
    else:
        console.print("  No detected command for this kind.")
