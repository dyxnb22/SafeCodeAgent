"""Command line entrypoint for SafeCode Agent."""

import sys
import typer
from pathlib import Path
from rich.panel import Panel

from safecode.cli_agent import agent_app
from safecode.cli_context import context_app
from safecode.cli_core import core_app, trust_app
from safecode.cli_mcp import mcp_app, mcp_discard
from safecode.cli_ops import audit_app, export_app, hooks_app, ide_app, logs_app, ops_app, queue_app, release_app, report_app
from safecode.cli_project import config_app, index_app, progress_app, skills_app, tools_app
from safecode.cli_sandbox import sandbox_app
from safecode.cli_subagent import subagent_app
from safecode.cli_test_demo import demo_app, test_app
from safecode.cli_api import api_app
from safecode.cli_tui import tui_app
from safecode.cli_shared import console
from safecode.cli_quickstart import register as _register_quickstart
from safecode.cli_fix import register as _register_fix
from safecode.cli_task import task_app
from safecode.cli_status import register as _register_status
from safecode.cli_resume import register as _register_resume
from safecode.cli_commit import register as _register_commit
from safecode.cli_profile import profile_app
from safecode.cli_memory import memory_app
from safecode.cli_debug import debug_app
from safecode.cli_smoke import smoke_app
from safecode.cli_shell import register as _register_shell
from safecode.config import SafeCodeConfig, _stricter_policy
from safecode.setup import write_setup

_WIZARD_STATIC_TEMPLATE = """\
# SafeCode Setup Template
# (Non-interactive mode — fill in values and run: sac setup --provider <p> --policy <policy>)

provider = "mock"          # or: openai, anthropic
model = "gpt-4.1-mini"    # model name for the selected provider
policy = "balanced"        # strict | balanced | experimental
network = false            # set true only if you need live LLM calls
"""

_KNOWN_PROVIDERS = {"mock", "openai", "anthropic"}
_KNOWN_POLICIES = {"strict", "balanced", "experimental", "normal", "learning"}


def run_setup_wizard(project_root: Path, *, is_tty: bool | None = None) -> int:
    """Interactive setup wizard. Returns exit code."""
    if is_tty is None:
        is_tty = sys.stdin.isatty()

    if not is_tty:
        console.print(_WIZARD_STATIC_TEMPLATE)
        return 0

    console.print("[bold]SafeCode Setup Wizard[/bold]")
    console.print("Press Enter to accept the default shown in [dim]brackets[/dim].\n")

    # Provider
    provider = typer.prompt("LLM provider (mock/openai/anthropic)", default="mock").strip().lower()
    if provider not in _KNOWN_PROVIDERS:
        console.print(f"[red]Unknown provider '{provider}'. Defaulting to mock.[/red]")
        provider = "mock"
    if provider != "mock":
        confirmed = typer.confirm(
            f"Switching to provider '{provider}' requires a real API key and network access. Continue?",
            default=False,
        )
        if not confirmed:
            console.print("[yellow]Keeping provider=mock.[/yellow]")
            provider = "mock"

    # Model
    default_model = "gpt-4.1-mini" if provider in {"mock", "openai"} else "claude-sonnet-4-6"
    model = typer.prompt("Model name", default=default_model).strip()

    # Policy
    policy_raw = typer.prompt(
        "Safety policy (strict/balanced/experimental)", default="balanced"
    ).strip().lower()
    if policy_raw not in _KNOWN_POLICIES:
        console.print(f"[red]Unknown policy '{policy_raw}'. Defaulting to balanced.[/red]")
        policy_raw = "balanced"

    # Network
    network = False
    if typer.confirm("Enable network access?", default=False):
        network = typer.confirm("Confirm: enable real network calls (LLM provider must support)?", default=False)

    # Refuse to lower user-level safety
    user_config = SafeCodeConfig.load(project_root)
    effective_policy = _stricter_policy(user_config.policy, policy_raw)
    if effective_policy != policy_raw:
        console.print(
            f"[yellow]Wizard: policy '{policy_raw}' is less restrictive than the current "
            f"user-level policy '{user_config.policy}'. "
            f"Using '{effective_policy}' to preserve user-level safety.[/yellow]"
        )
        policy_raw = effective_policy

    console.print(
        f"\n[bold]Summary:[/bold] provider={provider}, model={model}, "
        f"policy={policy_raw}, network={str(network).lower()}"
    )
    if not typer.confirm("Write this configuration?", default=False):
        console.print("[yellow]Setup cancelled.[/yellow]")
        return 0

    try:
        result = write_setup(
            project_root,
            provider=provider,
            model=model,
            policy=policy_raw,
            network_enabled=network,
        )
    except (FileExistsError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    console.print(
        Panel.fit(
            "\n".join([
                f"Config: {result.config_path}",
                f"Provider: {result.provider}",
                f"Model: {result.model}",
                f"Policy: {result.policy}",
                f"Network: {str(result.network_enabled).lower()}",
            ]),
            title="SafeCode Setup",
        )
    )
    return 0

app = typer.Typer(
    name="sac",
    help="SafeCode Agent: safety-first terminal coding assistant.",
    no_args_is_help=True,
)


@app.callback()
def callback() -> None:
    """Keep Typer in multi-command mode."""


@app.command("setup")
def setup(
    provider: str = typer.Option("mock", "--provider", help="LLM provider: mock or openai."),
    model: str = typer.Option("gpt-4.1-mini", "--model", help="Model name for the selected provider."),
    policy: str = typer.Option("balanced", "--policy", help="Safety preset: strict, balanced, experimental (or legacy: normal, learning)."),
    network: bool = typer.Option(False, "--network/--no-network", help="Enable network access in project config."),
    approval_dir: str = typer.Option("", "--approval-dir", help="External hook approval directory."),
    sandbox_approval_dir: str = typer.Option("", "--sandbox-approval-dir", help="External sandbox approval directory."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing setup files."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept the selected options without prompting."),
    wizard: bool = typer.Option(False, "--wizard", help="Interactive wizard: walks provider/model/policy; non-TTY prints static template."),
) -> None:
    """Configure model, network, approval dirs, and safety preset."""
    if wizard:
        code = run_setup_wizard(Path.cwd())
        raise typer.Exit(code=code)
    if not yes:
        confirmed = typer.confirm(
            f"Write SafeCode setup with provider={provider}, policy={policy}, network={network}?",
            default=False,
        )
        if not confirmed:
            console.print("[yellow]Setup cancelled.[/yellow]")
            raise typer.Exit(code=0)
    try:
        result = write_setup(
            Path.cwd(),
            provider=provider,
            model=model,
            policy=policy,
            network_enabled=network,
            approval_dir=Path(approval_dir) if approval_dir else None,
            sandbox_approval_dir=Path(sandbox_approval_dir) if sandbox_approval_dir else None,
            force=force,
        )
    except (FileExistsError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            "\n".join(
                [
                    f"Config: {result.config_path}",
                    f"Env: {result.env_path}",
                    f"Provider: {result.provider}",
                    f"Model: {result.model}",
                    f"Policy: {result.policy}",
                    f"Network: {str(result.network_enabled).lower()}",
                    f"Approval dir: {result.approval_dir}",
                    f"Sandbox approval dir: {result.sandbox_approval_dir}",
                ]
            ),
            title="SafeCode Setup",
        )
    )


_register_quickstart(app)
_register_fix(app)
_register_status(app)
_register_resume(app)
_register_commit(app)
_register_shell(app)

# Core commands stay at the root for backward compatibility.
for command in core_app.registered_commands:
    app.registered_commands.append(command)
for command in ops_app.registered_commands:
    app.registered_commands.append(command)

app.add_typer(task_app, name="task")
app.add_typer(profile_app, name="profile")
app.add_typer(memory_app, name="memory")
app.add_typer(debug_app, name="debug")
app.add_typer(context_app, name="context", hidden=True)
app.add_typer(trust_app, name="trust", hidden=True)
app.add_typer(config_app, name="config", hidden=True)
app.add_typer(skills_app, name="skills", hidden=True)
app.add_typer(tools_app, name="tools", hidden=True)
app.add_typer(index_app, name="index", hidden=True)
app.add_typer(progress_app, name="progress", hidden=True)
app.add_typer(mcp_app, name="mcp", hidden=True)
app.add_typer(subagent_app, name="subagent", hidden=True)
app.add_typer(queue_app, name="queue", hidden=True)
app.add_typer(export_app, name="export", hidden=True)
app.add_typer(ide_app, name="ide", hidden=True)
app.add_typer(release_app, name="release", hidden=True)
app.add_typer(logs_app, name="logs", hidden=True)
app.add_typer(audit_app, name="audit", hidden=True)
app.add_typer(hooks_app, name="hooks", hidden=True)
app.add_typer(sandbox_app, name="sandbox", hidden=True)
app.add_typer(agent_app, name="agent", hidden=True)
app.add_typer(test_app, name="test", hidden=True)
app.add_typer(demo_app, name="demo", hidden=True)
app.add_typer(tui_app, name="tui", hidden=True)
app.add_typer(api_app, name="api", hidden=True)
app.add_typer(report_app, name="report", hidden=True)
app.add_typer(smoke_app, name="smoke", hidden=True)


def main() -> None:
    """Console script entrypoint."""
    app()


if __name__ == "__main__":
    main()
