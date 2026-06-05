"""quickstart command: guided first-run onboarding for new users."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from safecode.cli_shared import console
from safecode.config import SafeCodeConfig
from safecode.demo.workflows import DemoWorkflowSuite
from safecode.setup import SetupResult, write_setup

_RECOMMENDED_DEMO = "cli-version-flag"

_NEXT_STEPS = """\
Next steps:
  sac ask "What does this project do?"
  sac edit "Add a docstring to main()"
  sac apply
  sac rollback --last
"""

_NEXT_STEPS_PYTHON = """\
Next steps:
  sac ask "What does this project do?"
  sac edit "Add a docstring to main()"
  sac apply
  sac fix                    # auto-repair a failing pytest test
  sac rollback --last
"""

_NEXT_STEPS_TYPESCRIPT = """\
Next steps:
  sac ask "What does this project do?"
  sac edit "Add a JSDoc comment to the main export"
  sac apply
  sac fix --test-command "npm test"
  sac rollback --last
"""

_NEXT_STEPS_GO = """\
Next steps:
  sac ask "What does this project do?"
  sac edit "Add a comment to the main package"
  sac apply
  sac fix --test-command "go test ./..."
  sac rollback --last
"""

_NEXT_STEPS_RUST = """\
Next steps:
  sac ask "What does this project do?"
  sac edit "Add a doc comment to a public function"
  sac apply
  sac fix --test-command "cargo test"
  sac rollback --last
"""


def _detect_stack(project_root: Path) -> str:
    """Return the primary detected stack: python, typescript, go, rust, or unknown."""
    if (project_root / "pyproject.toml").exists():
        return "python"
    if (project_root / "package.json").exists():
        return "typescript"
    if (project_root / "go.mod").exists():
        return "go"
    if (project_root / "Cargo.toml").exists():
        return "rust"
    return "unknown"


def _next_steps_for_stack(stack: str) -> str:
    return {
        "python": _NEXT_STEPS_PYTHON,
        "typescript": _NEXT_STEPS_TYPESCRIPT,
        "go": _NEXT_STEPS_GO,
        "rust": _NEXT_STEPS_RUST,
    }.get(stack, _NEXT_STEPS)


def _demo_id_for_stack(stack: str) -> str:
    return _RECOMMENDED_DEMO


def _provider_is_ready(project_root: Path) -> bool:
    """Return True if a live provider is configured with key and network enabled."""
    import os
    config = SafeCodeConfig.load(project_root)
    provider = config.llm.provider
    if provider == "mock":
        return False
    if not config.sandbox.network_enabled:
        return False
    # Check API key: env var or user config
    if provider == "deepseek":
        from safecode.llm.deepseek import DEEPSEEK_PRESET
        env_name = DEEPSEEK_PRESET.api_key_env
    elif provider in ("openai", "openai-compatible"):
        env_name = "OPENAI_API_KEY"
    elif provider == "anthropic":
        env_name = "ANTHROPIC_API_KEY"
    else:
        env_name = "OPENAI_API_KEY"
    if os.getenv(env_name) or os.getenv("SAFECODE_LLM_API_KEY") or getattr(config.llm, "api_key", None):
        return True
    # Check provider profiles
    from safecode.llm.provider_profiles import get_active_profile
    try:
        from safecode.config import _user_config_path
        profile = get_active_profile(_user_config_path().expanduser())
        if profile and profile.api_key_source() != "missing":
            return True
    except Exception:
        pass
    return False


def _show_config_summary(project_root: Path) -> None:
    config = SafeCodeConfig.load(project_root)
    table = Table(title="Current SafeCode Config", show_header=False)
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("Provider", config.llm.provider)
    table.add_row("Model", config.llm.model)
    table.add_row("Policy", config.policy)
    table.add_row("Network", str(config.sandbox.network_enabled).lower())
    console.print(table)


def _ensure_config(project_root: Path, force: bool) -> Optional[SetupResult]:
    """Write default config if none exists. Returns SetupResult or None if skipped."""
    config_path = project_root / ".sac" / "config.toml"
    if config_path.exists() and not force:
        return None
    try:
        return write_setup(
            project_root,
            provider="mock",
            model="gpt-4.1-mini",
            policy="balanced",
            force=force,
        )
    except FileExistsError:
        return None


def run_quickstart(
    project_root: Path,
    *,
    yes: bool = False,
    force: bool = False,
    demo: bool = False,
    demo_id: str = _RECOMMENDED_DEMO,
    demo_dest: Path | None = None,
) -> int:
    """Core quickstart logic, returns exit code. Extracted for testability."""
    config_path = project_root / ".sac" / "config.toml"
    already_configured = config_path.exists() and not force

    if already_configured:
        console.print("[green]Found existing .sac/config.toml — skipping init.[/green]")
    else:
        if not yes:
            confirmed = typer.confirm(
                "No .sac/config.toml found. Create default config (provider=mock, policy=balanced)?",
                default=True,
            )
            if not confirmed:
                console.print("[yellow]Quickstart cancelled.[/yellow]")
                return 0
        result = _ensure_config(project_root, force=force)
        if result:
            console.print(f"[green]Created config: {result.config_path}[/green]")

    _show_config_summary(project_root)

    # Detect stack and adapt demo + next steps.
    stack = _detect_stack(project_root)
    if stack != "unknown":
        console.print(f"[blue]Detected stack:[/blue] {stack}")

    # Check if provider is ready before recommending a live-provider demo.
    provider_ready = _provider_is_ready(project_root)

    if not provider_ready:
        console.print(
            Panel.fit(
                "[yellow]Provider not ready — live demo requires a configured provider with API key and network.[/yellow]\n"
                "Run: [bold]sac doctor[/bold] for setup steps.",
                title="SafeCode Quickstart",
            )
        )
    else:
        effective_demo_id = demo_id if demo_id != _RECOMMENDED_DEMO else _demo_id_for_stack(stack)

        # Recommend a demo workflow.
        suite = DemoWorkflowSuite()
        try:
            workflow = suite.get(effective_demo_id)
        except KeyError:
            workflow = suite.list()[0]

        console.print(
            Panel.fit(
                "\n".join(
                    [
                        f"Recommended demo: [bold]{workflow.id}[/bold]",
                        f"  Title   : {workflow.title}",
                        f"  Task    : {workflow.task}",
                        f"  Commands: {' -> '.join(workflow.commands)}",
                        *(([f"  Stack   : {stack}"]) if stack != "unknown" else []),
                    ]
                ),
                title="SafeCode Quickstart",
            )
        )

    if demo:
        # Explicit --demo flag: materialize the project regardless of provider state.
        effective_demo_id = demo_id if demo_id != _RECOMMENDED_DEMO else _demo_id_for_stack(stack)
        suite = DemoWorkflowSuite()
        try:
            workflow = suite.get(effective_demo_id)
        except KeyError:
            workflow = suite.list()[0]
        dest = demo_dest or project_root / "examples" / "demo-workflows"
        dest.mkdir(parents=True, exist_ok=True)
        try:
            demo_root = suite.materialize(workflow.id, dest, force=force)
            console.print(f"[green]Demo project created: {demo_root}[/green]")
            console.print(f"  cd {demo_root}")
        except FileExistsError as exc:
            console.print(f"[yellow]Demo already exists ({exc}). Use --force to overwrite.[/yellow]")

    console.print(_next_steps_for_stack(stack))
    return 0


def register(app: typer.Typer) -> None:
    """Register the quickstart command on the given Typer app."""

    @app.command("quickstart", hidden=True)
    def quickstart(
        yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts."),
        force: bool = typer.Option(False, "--force", help="Overwrite existing config."),
        demo: bool = typer.Option(False, "--demo", help="Materialize the recommended demo workflow."),
        demo_id: str = typer.Option(_RECOMMENDED_DEMO, "--demo-id", help="Demo workflow to recommend/materialize."),
        demo_dest: Optional[Path] = typer.Option(None, "--demo-dest", help="Destination for demo project."),
    ) -> None:
        """Guided first-run: check config, show provider/policy, recommend a demo, print next steps."""
        code = run_quickstart(
            Path.cwd(),
            yes=yes,
            force=force,
            demo=demo,
            demo_id=demo_id,
            demo_dest=demo_dest,
        )
        raise typer.Exit(code=code)
