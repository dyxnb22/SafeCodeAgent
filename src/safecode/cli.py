"""Command line entrypoint for SafeCode Agent."""

import sys
import typer
from pathlib import Path
from rich.panel import Panel
from typer import Context

from safecode.cli_agent import agent_app
from safecode.cli_context import context_app
from safecode.cli_core import core_app, trust_app
from safecode.cli_mcp import mcp_app, mcp_discard
from safecode.cli_ops import audit_app, export_app, hooks_app, ide_app, logs_app, ops_app, queue_app, release_app, report_app
from safecode.cli_project import config_app, index_app, progress_app, skills_app, tools_app
from safecode.cli_sandbox import sandbox_app
from safecode.cli_subagent import subagent_app
from safecode.cli_test_demo import demo_app, test_app
from safecode.cli_testgen import testgen_app
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
from safecode.cli_refactor import refactor_app
from safecode.cli_smoke import smoke_app
from safecode.cli_shell import register as _register_shell
from safecode.cli_lsp import lsp_app
from safecode.cli_session import session_app
from safecode.cli_format import format_app
from safecode.cli_shell import run_shell
from safecode.cli_model import register as _register_model
from safecode.cli_init import register as _register_init
from safecode.cli_provider import provider_app
from safecode.config import SafeCodeConfig, _stricter_policy
from safecode.setup import write_setup

_WIZARD_STATIC_TEMPLATE = """\
# SafeCode Setup Template
# (Non-interactive mode — fill in values and run: sac setup --provider <p> --policy <policy>)

provider = "mock"          # or: deepseek, openai, openai-compatible
model = "gpt-4.1-mini"    # model name for the selected provider
policy = "balanced"        # strict | balanced | experimental
network = false            # set true only if you need live LLM calls
"""

_KNOWN_PROVIDERS = {"mock", "openai", "openai-compatible", "deepseek"}
_KNOWN_POLICIES = {"strict", "balanced", "experimental", "normal", "learning"}

# Default model per provider for the wizard prompt.
_WIZARD_DEFAULT_MODELS: dict[str, str] = {
    "mock": "gpt-4.1-mini",
    "openai": "gpt-4.1-mini",
    "openai-compatible": "gpt-4.1-mini",
    "deepseek": "deepseek-v4-flash",
}


def run_setup_wizard(project_root: Path, *, is_tty: bool | None = None) -> int:
    """Interactive setup wizard. Returns exit code."""
    if is_tty is None:
        is_tty = sys.stdin.isatty()

    if not is_tty:
        console.print(_WIZARD_STATIC_TEMPLATE)
        return 0

    console.print("[bold]SafeCode Setup Wizard[/bold]")
    console.print("Press Enter to accept the default shown in [dim]brackets[/dim].\n")

    # Provider — offer mock, deepseek, openai, openai-compatible.
    # Anthropic is intentionally not advertised in the v4.10 wizard (deferred).
    provider = typer.prompt(
        "LLM provider (mock/deepseek/openai/openai-compatible)", default="mock"
    ).strip().lower()
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

    # DeepSeek-specific reminder (informational only; never prompt for the key).
    if provider == "deepseek":
        console.print(
            "[yellow]DeepSeek (EXPERIMENTAL): set the DEEPSEEK_API_KEY environment variable "
            "before running sac. Never write the key to disk.[/yellow]"
        )

    # Model
    default_model = _WIZARD_DEFAULT_MODELS.get(provider, "gpt-4.1-mini")
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
    no_args_is_help=False,
    invoke_without_command=True,
)


@app.callback()
def callback(
    ctx: Context,
    model: str = typer.Option("", "--model", help="One-shot model override for this invocation (e.g. pro or deepseek:pro)."),
) -> None:
    """Enter the interactive shell when `sac` is invoked without a subcommand."""
    if model:
        from safecode.cli_model import apply_model_override_env
        try:
            apply_model_override_env(model)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc
    if ctx.invoked_subcommand is None:
        code = run_shell(Path.cwd(), is_tty=sys.stdin.isatty() and sys.stdout.isatty())
        raise typer.Exit(code=code)


@app.command("help", hidden=True)
def help_all_cmd(
    all_cmds: bool = typer.Option(False, "--all", "-a", help="Show all commands including hidden/advanced."),
) -> None:
    """Show help. With --all, prints the full command surface."""
    if all_cmds:
        console.print("[bold]SafeCode Agent — Full Command Surface[/bold]")
        console.print("")
        console.print("[bold]Daily Commands (v4.16+):[/bold]")
        console.print("  init        Guided first-run: provider, key, model, policy")
        console.print("  ask         Ask a read-only question about the project")
        console.print("  edit        Create a pending patch proposal")
        console.print("  apply       Apply the latest pending patch after review")
        console.print("  fix         Run failing test, propose repair patch")
        console.print("  commit      Commit files touched by the current task")
        console.print("  doctor      Check local install and project environment")
        console.print("")
        console.print("[bold]Advanced & Experimental (callable, hidden from sac --help):[/bold]")
        console.print("  quickstart  Guided first-run with demo recommendation")
        console.print("  status      Show current task and pending patch state")
        console.print("  task        Manage task sidecars")
        console.print("  rollback    Rollback a previous applied patch")
        console.print("  run         Run a shell command through risk checks")
        console.print("  profile     Manage project command profiles")
        console.print("  resume      Resume an interrupted task")
        console.print("  memory      Inspect and update project memory")
        console.print("  debug       Inspect debug artifacts")
        console.print("  shell       Interactive AI shell session")
        console.print("  model       Show or switch the model configuration")
        console.print("  provider    Manage provider profiles")
        console.print("  tools       List built-in, MCP, and user-declared tools")
        console.print("  mcp         Manage MCP servers and read/write proposals")
        console.print("  refactor    Semantic refactor commands such as rename")
        console.print("  test-gen    Generate test patches for files or symbols")
        console.print("  lsp         Inspect terminal language-service diagnostics")
        console.print("  session     List, export, import, and summarize sessions")
        console.print("  format      Detect and run project formatters")
        console.print("  version     Show package version")
        console.print("  setup       Write .sac/config.toml")
        console.print("")
        console.print("[bold]Shell Slash Commands (sac shell):[/bold]")
        console.print("  /status  /task  /model  /provider status  /apply")
        console.print("  /mode  /history  /compact  /undo  /commit  /debug  /help  /exit")
        console.print("")
        console.print("[dim]All commands remain callable. Run --help on any command for details.[/dim]")
    else:
        console.print("Use [bold]sac help --all[/bold] for the full command list.")


@app.command("setup", hidden=True)
def setup(
    provider: str = typer.Option("mock", "--provider", help="LLM provider: mock or openai."),
    model: str = typer.Option("gpt-4.1-mini", "--model", help="Model name for the selected provider."),
    policy: str = typer.Option("balanced", "--policy", help="Safety preset: strict, balanced, experimental (or legacy: normal, learning)."),
    network: bool = typer.Option(False, "--network/--no-network", help="Enable network access in project config."),
    approval_dir: str = typer.Option("", "--approval-dir", help="External hook approval directory."),
    sandbox_approval_dir: str = typer.Option("", "--sandbox-approval-dir", help="External sandbox approval directory."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing setup files."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept the selected options without prompting."),
    wizard: bool = typer.Option(False, "--wizard", help="Interactive wizard: walks provider/model/policy; non-TTY prints static template. (deprecated, prefer `sac init`)"),
) -> None:
    """Configure model, network, approval dirs, and safety preset."""
    if wizard:
        console.print("[dim]setup --wizard is deprecated in v4.15.0; prefer `sac init`.[/dim]")
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
_register_model(app)
_register_init(app)

# Core commands stay at the root for backward compatibility.
for command in core_app.registered_commands:
    app.registered_commands.append(command)
for command in ops_app.registered_commands:
    app.registered_commands.append(command)

app.add_typer(task_app, name="task", hidden=True)
app.add_typer(provider_app, name="provider", hidden=True)
app.add_typer(profile_app, name="profile", hidden=True)
app.add_typer(memory_app, name="memory", hidden=True)
app.add_typer(debug_app, name="debug", hidden=True)
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
app.add_typer(refactor_app, name="refactor", hidden=True)  # v6.9.1
app.add_typer(testgen_app, name="test-gen", hidden=True)
app.add_typer(lsp_app, name="lsp", hidden=True)
app.add_typer(session_app, name="session", hidden=True)
app.add_typer(format_app, name="format", hidden=True)


@app.command("why", hidden=True)
def why(
    ctx: Context,
) -> None:
    """Show the last failure's category and suggested next command (v4.16.2, EXPERIMENTAL).

    A shorter alias for: sac debug last-failure --short
    """
    from safecode.cli_debug import find_last_failure
    from safecode.core.failure_category import suggested_command_for_category

    failure = find_last_failure(Path.cwd())
    if failure is None:
        console.print("[dim]No recent failure recorded. Run 'sac logs show --level error' for details.[/dim]")
        return

    category = failure.category or "unknown"
    message = failure.message or "no details"
    cmd = failure.command or ""
    suggested = suggested_command_for_category(category)

    console.print(f"[bold]Problem:[/bold] {message}")
    console.print(f"[bold]Category:[/bold] {category}")
    if cmd:
        console.print(f"[bold]Command:[/bold] {cmd}")
    console.print(f"[bold]Next:[/bold] {suggested}")


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Natural-language search query."),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results to show."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Semantic + keyword hybrid search across project files.

    Combines path-token matching, git recency, and semantic embeddings (when
    the embedding index is built via 'sac index build').
    """
    from safecode.context.hybrid_retrieval import HybridRetriever
    from safecode.cli_shared_json import CLIJSONResponse, render_json

    project_root = Path.cwd()
    retriever = HybridRetriever(project_root)
    results = retriever.retrieve(query, limit=limit)

    if json_output:
        data = {
            "query": query,
            "results": [
                {
                    "path": r.path,
                    "combined_score": r.combined_score,
                    "keyword_score": r.keyword_score,
                    "semantic_score": r.semantic_score,
                    "selection_reason": r.selection_reason,
                }
                for r in results
            ],
        }
        print(render_json(CLIJSONResponse(command="search", status="success", data=data)))
        return

    if not results:
        console.print(f"[yellow]No results for: {query}[/yellow]")
        console.print("[dim]Tip: run 'sac index build' to enable semantic search.[/dim]")
        return

    from rich.table import Table
    table = Table(title=f"Search: {query}")
    table.add_column("Score", justify="right", style="cyan", no_wrap=True)
    table.add_column("File")
    table.add_column("Reason", style="dim")
    for r in results:
        table.add_row(f"{r.combined_score:.2f}", r.path, r.selection_reason)
    console.print(table)
    console.print(f"\n[dim]Tip: run 'sac index build' to enable semantic search.[/dim]")


def main() -> None:
    """Console script entrypoint."""
    app()


if __name__ == "__main__":
    main()
