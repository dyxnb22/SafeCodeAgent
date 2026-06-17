from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.cli_shared import console, log_cli_error, runtime_logger, show_human_checkpoint
from safecode.cli_shared_json import CLIJSONResponse, render_json

from safecode.config import SafeCodeConfig, ensure_config_file
from safecode.index.files import FileIndexer
from safecode.index.python_symbols import PythonSymbolIndexer
from safecode.index.repo_map import RepoMapBuilder
from safecode.skills.loader import SkillLoader
from safecode.state.progress import ProgressState, ProgressStore
from safecode.tools.registry import PermissionCategory, ToolRegistry, ToolRiskLevel
from safecode.policy.audit import audit_policy, diff_policy, render_policy_audit, render_policy_diff

config_app = typer.Typer(help="Manage SafeCode project config.")
skills_app = typer.Typer(help="List and inspect skills.")
tools_app = typer.Typer(help="List and inspect internal tool schemas.")
index_app = typer.Typer(help="Build lightweight project indexes.")
progress_app = typer.Typer(help="Read and update long-running progress.")


@config_app.command("init")
def config_init() -> None:
    """Create .sac/config.toml."""
    path = ensure_config_file(Path.cwd())
    console.print(f"Config ready: {path}")


@config_app.command("show")
def config_show() -> None:
    """Show effective SafeCode config."""
    config = SafeCodeConfig.load(Path.cwd())
    console.print(Syntax(config.to_toml(), "toml", theme="ansi_dark"))


@config_app.command("policy-audit")
def config_policy_audit() -> None:
    """Audit policy presets, aliases, unknown names, and safety invariants."""
    result = audit_policy(Path.cwd())
    console.print(render_policy_audit(result))
    if not result.ok:
        raise typer.Exit(1)


@config_app.command("migrate")
def config_migrate(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Migrate legacy [llm] config to [providers.<name>] format (v4.16.1).

    Reads the trusted user config, converts any [llm] provider/model/api_key/
    base_url settings into a new provider profile under [providers], writes a
    .bak backup, and saves the migrated config. Safe to re-run.
    """
    import shutil
    import tomllib
    from safecode.config import _user_config_path
    from safecode.llm.provider_profiles import _render_user_toml, _PROVIDER_PRESETS
    path = _user_config_path().expanduser()

    if not path.exists():
        console.print("[yellow]No user config found. Nothing to migrate.[/yellow]")
        return

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    llm = data.get("llm", {})
    if not isinstance(llm, dict) or not llm:
        console.print("[dim]No legacy [llm] section found. Nothing to migrate.[/dim]")
        return

    provider_name = str(llm.get("provider", "")).strip()
    if not provider_name or provider_name == "mock":
        console.print("[dim]Provider is mock or unset. Nothing to migrate.[/dim]")
        return

    if not yes:
        confirmed = typer.confirm(
            f"Migrate legacy [llm] config to [providers.{provider_name}]? "
            f"A backup will be saved to {path}.bak",
            default=True,
        )
        if not confirmed:
            console.print("[yellow]Migration cancelled.[/yellow]")
            return

    # Write backup
    backup_path = Path(str(path) + ".bak")
    shutil.copy2(path, backup_path)
    console.print(f"Backup saved: {backup_path}")

    # Build provider profile from legacy config
    providers = dict(data.get("providers", {}))
    existing = dict(providers.get(provider_name, {})) if isinstance(providers.get(provider_name), dict) else {}
    existing.setdefault("base_url", str(llm.get("base_url", "")))
    existing.setdefault("default_model", str(llm.get("model", "")))
    if llm.get("api_key") and not existing.get("api_key"):
        existing["api_key"] = str(llm["api_key"])
    # Preserve network allowlist from preset if not already set
    preset = _PROVIDER_PRESETS.get(provider_name, {})
    if not existing.get("network_allowlist"):
        existing["network_allowlist"] = list(preset.get("network_allowlist", []))
    if not existing.get("model_aliases"):
        existing["model_aliases"] = dict(preset.get("model_aliases", {}))

    providers[provider_name] = existing
    data["providers"] = providers
    if "active" not in providers:
        providers["active"] = provider_name

    # Remove legacy [llm] api_key from the saved data (keep rest for reference)
    if "api_key" in data.get("llm", {}):
        del data["llm"]["api_key"]

    path.write_text(_render_user_toml(data), encoding="utf-8")
    try:
        import os
        os.chmod(path, 0o600)
    except OSError:
        pass

    console.print(f"[green]Migrated legacy [llm] to [providers.{provider_name}] in {path}[/green]")
    console.print("[dim]Remove the [llm] section manually if no longer needed.[/dim]")


@config_app.command("diff")
def config_diff(
    against: str = typer.Option(..., "--against", help="Compare against preset: strict, balanced, experimental."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Show knob-by-knob delta between effective config and a named preset."""
    try:
        result = diff_policy(Path.cwd(), against)
    except ValueError as exc:
        if json_output:
            print(render_json(CLIJSONResponse(command="config diff", status="error", error=str(exc))))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    if json_output:
        print(
            render_json(
                CLIJSONResponse(
                    command="config diff",
                    status="success",
                    data=result.to_dict(),
                )
            )
        )
        return
    console.print(render_policy_diff(result))


@skills_app.command("list")
def skills_list() -> None:
    """List local skills."""
    skills = SkillLoader(Path.cwd()).list()
    table = Table(title="SafeCode Skills")
    table.add_column("Name")
    table.add_column("Path")
    for skill in skills:
        table.add_row(skill.name, str(skill.path))
    console.print(table if skills else "[yellow]No skills found.[/yellow]")


@skills_app.command("show")
def skills_show(name: str) -> None:
    """Show one skill."""
    skill = SkillLoader(Path.cwd()).get(name)
    console.print(Panel(skill.instructions, title=skill.name))


@tools_app.command("list")
def tools_list(
    risk: Optional[str] = typer.Option(None, "--risk", help="Filter by risk level (low, medium, high)."),
    permission: Optional[str] = typer.Option(None, "--permission", help="Filter by permission category."),
    include_mcp: bool = typer.Option(False, "--include-mcp", help="Include configured MCP native tools."),
    include_user: bool = typer.Option(False, "--include-user", help="Include user-declared tools from .sac/tools.toml."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """List built-in tool schemas with risk and permission metadata."""
    registry = ToolRegistry()
    tools = registry.list()

    if risk:
        try:
            risk_level = ToolRiskLevel(risk.lower())
        except ValueError:
            console.print(f"[red]Unknown risk level: {risk!r}. Use low, medium, or high.[/red]")
            raise typer.Exit(1)
        tools = [t for t in tools if t.risk == risk_level]

    if permission:
        try:
            perm_cat = PermissionCategory(permission.lower())
        except ValueError:
            valid = ", ".join(c.value for c in PermissionCategory)
            console.print(f"[red]Unknown permission category: {permission!r}. Use one of: {valid}[/red]")
            raise typer.Exit(1)
        tools = [t for t in tools if t.permission_category == perm_cat]

    mcp_tools: list[dict] = []
    if include_mcp:
        try:
            from safecode.agent.native_dispatcher import NativeToolDispatcher
            from safecode.mcp.native_bridge import register_mcp_tools

            dispatcher = NativeToolDispatcher()
            register_mcp_tools(dispatcher, Path.cwd())
            mcp_tools = [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "requires_approval": spec.requires_approval,
                    "experimental": spec.experimental,
                    "source": "mcp",
                }
                for spec in dispatcher.specs()
            ]
        except Exception:
            mcp_tools = []

    user_tools: list[dict] = []
    user_tool_errors: list[str] = []
    if include_user:
        from safecode.tools.user_config import load_user_tool_specs

        specs, user_tool_errors = load_user_tool_specs(Path.cwd())
        user_tools = [
            {
                "name": tool.name,
                "risk": tool.risk.value,
                "permission": tool.permission_category.value,
                "requires_approval": tool.requires_human_approval,
                "description": tool.description,
                "source": "user",
            }
            for tool in specs
        ]

    if json_output:
        print(render_json(CLIJSONResponse(
            command="tools list",
            status="success",
            data={
                "tools": [
                    {
                        "name": tool.name,
                        "risk": tool.risk.value,
                        "permission": tool.permission_category.value,
                        "requires_approval": tool.requires_human_approval,
                        "description": tool.description,
                        "source": "builtin",
                    }
                    for tool in tools
                ],
                "mcp_tools": mcp_tools,
                "user_tools": user_tools,
                "user_tool_errors": user_tool_errors,
            },
        )))
        return

    table = Table(title="SafeCode Internal Tools")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Risk")
    table.add_column("Permission")
    table.add_column("Approval", justify="center")
    table.add_column("Description")
    for tool in tools:
        approval_marker = "[yellow]yes[/yellow]" if tool.requires_human_approval else "[green]no[/green]"
        table.add_row(tool.name, tool.risk, tool.permission_category, approval_marker, tool.description)
    console.print(table if tools else "[yellow]No tools match the given filters.[/yellow]")
    if include_mcp:
        mcp_table = Table(title="Configured MCP Native Tools")
        mcp_table.add_column("Name", style="cyan", no_wrap=True)
        mcp_table.add_column("Approval", justify="center")
        mcp_table.add_column("Description")
        for tool in mcp_tools:
            approval_marker = "[yellow]yes[/yellow]" if tool["requires_approval"] else "[green]no[/green]"
            mcp_table.add_row(tool["name"], approval_marker, tool["description"])
        console.print(mcp_table if mcp_tools else "[yellow]No MCP native tools discovered.[/yellow]")
    if include_user:
        user_table = Table(title="User-declared Tools")
        user_table.add_column("Name", style="cyan", no_wrap=True)
        user_table.add_column("Risk")
        user_table.add_column("Permission")
        user_table.add_column("Approval", justify="center")
        user_table.add_column("Description")
        for tool in user_tools:
            approval_marker = "[yellow]yes[/yellow]" if tool["requires_approval"] else "[green]no[/green]"
            user_table.add_row(tool["name"], tool["risk"], tool["permission"], approval_marker, tool["description"])
        console.print(user_table if user_tools else "[yellow]No user tools discovered.[/yellow]")
        for error in user_tool_errors:
            console.print(f"[yellow]User tool config warning: {error}[/yellow]")


@tools_app.command("inspect")
def tools_inspect(name: str = typer.Argument(..., help="Tool name to inspect.")) -> None:
    """Show full schema for a single tool including arguments and audit event."""
    registry = ToolRegistry()
    try:
        tool = registry.get(name)
    except KeyError:
        console.print(f"[red]Unknown tool: {name!r}[/red]")
        console.print(f"Available tools: {', '.join(registry.names())}")
        raise typer.Exit(1)

    from rich.panel import Panel as _Panel

    approval_text = "[yellow]required[/yellow]" if tool.requires_human_approval else "[green]not required[/green]"
    lines = [
        f"[bold]Description:[/bold] {tool.description}",
        f"[bold]Risk:[/bold]        {tool.risk}",
        f"[bold]Permission:[/bold]  {tool.permission_category}",
        f"[bold]Approval:[/bold]    {approval_text}",
    ]
    if tool.args:
        lines.append("\n[bold]Arguments:[/bold]")
        for arg in tool.args:
            req = "required" if arg.required else "optional"
            lines.append(f"  • {arg.name} ({arg.type}, {req}): {arg.description}")
    else:
        lines.append("\n[bold]Arguments:[/bold] none")
    if tool.audit_event:
        lines.append(f"\n[bold]Audit Event:[/bold] {tool.audit_event.event_type} — {tool.audit_event.description}")
    else:
        lines.append("\n[bold]Audit Event:[/bold] none")

    console.print(_Panel("\n".join(lines), title=f"[bold cyan]{tool.name}[/bold cyan]", expand=False))


@index_app.command("build")
def index_build(
    force: bool = typer.Option(False, "--force", help="Re-embed all chunks even if unchanged."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Build or update the local embedding index."""
    from safecode.index.embedding_store import EmbeddingStore
    from safecode.cli_shared_json import CLIJSONResponse, render_json
    project_root = Path.cwd()
    sac_dir = project_root / ".sac"
    store = EmbeddingStore(sac_dir)
    files = [item.path for item in FileIndexer(project_root).index()]
    result = store.build(files, project_root, force=force)
    status = store.status()
    if json_output:
        print(render_json(CLIJSONResponse(command="index build", status="success", data={**result, **status.to_dict()})))
        return
    backend_label = f"[green]{status.model_id}[/green]" if status.is_semantic else "[yellow]null (keyword-only fallback)[/yellow]"
    console.print(f"[bold]Embedding backend:[/bold] {backend_label}")
    if not status.is_semantic:
        console.print("[yellow]Semantic search inactive (null backend).[/yellow]")
        console.print("[dim]To enable: pip install 'safecode-agent[semantic]'[/dim]")
    console.print(f"Files indexed : {result['files_indexed']}")
    console.print(f"Chunks added  : {result['chunks_added']}")
    console.print(f"Chunks skipped: {result['chunks_skipped']} (unchanged)")
    console.print(f"Total chunks  : {status.total_chunks}")


@index_app.command("status")
def index_status(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Show embedding index status."""
    from safecode.index.embedding_store import EmbeddingStore
    from safecode.cli_shared_json import CLIJSONResponse, render_json
    sac_dir = Path.cwd() / ".sac"
    status = EmbeddingStore(sac_dir).status()
    if json_output:
        print(render_json(CLIJSONResponse(command="index status", status="success", data=status.to_dict())))
        return
    if not status.exists:
        console.print("[yellow]No embedding index found. Run: sac index build[/yellow]")
        return
    backend_label = f"[green]{status.model_id}[/green]" if status.is_semantic else "[yellow]null (keyword-only fallback)[/yellow]"
    console.print(f"[bold]Backend :[/bold] {backend_label}")
    if not status.is_semantic:
        console.print("[yellow]Semantic search inactive (null backend).[/yellow]")
        console.print("[dim]To enable: pip install 'safecode-agent[semantic]'[/dim]")
    console.print(f"Files   : {status.total_files}")
    console.print(f"Chunks  : {status.total_chunks}")
    console.print(f"Built   : {status.last_built or 'unknown'}")


@index_app.command("rebuild")
def index_rebuild(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Force-rebuild the embedding index, re-embedding all chunks."""
    from safecode.index.embedding_store import EmbeddingStore
    from safecode.cli_shared_json import CLIJSONResponse, render_json
    project_root = Path.cwd()
    sac_dir = project_root / ".sac"
    store = EmbeddingStore(sac_dir)
    files = [item.path for item in FileIndexer(project_root).index()]
    result = store.build(files, project_root, force=True)
    status = store.status()
    if json_output:
        print(render_json(CLIJSONResponse(command="index rebuild", status="success", data={**result, **status.to_dict()})))
        return
    backend_label = f"[green]{status.model_id}[/green]" if status.is_semantic else "[yellow]null (keyword-only fallback)[/yellow]"
    console.print(f"[bold]Embedding backend:[/bold] {backend_label}")
    console.print(f"Files indexed : {result['files_indexed']}")
    console.print(f"Chunks added  : {result['chunks_added']}")
    console.print(f"Chunks skipped: {result['chunks_skipped']}")
    console.print(f"Total chunks  : {status.total_chunks}")


@index_app.command("files")
def index_files() -> None:
    """List indexed files."""
    for item in FileIndexer(Path.cwd()).index():
        console.print(item.path)


@index_app.command("symbols")
def index_symbols() -> None:
    """List indexed Python symbols."""
    table = Table(title="Python Symbols")
    table.add_column("Kind")
    table.add_column("Name")
    table.add_column("Location")
    for symbol in PythonSymbolIndexer(Path.cwd()).index():
        table.add_row(symbol.kind, symbol.name, f"{symbol.path}:{symbol.line}")
    console.print(table)


@index_app.command("map")
def index_map(as_json: bool = typer.Option(False, "--json", help="Render full repo map as JSON.")) -> None:
    """Build a repo map with files, symbols, imports, tests, commands, and entrypoints."""
    repo_map = RepoMapBuilder(Path.cwd()).build()
    if as_json:
        console.print(Syntax(repo_map.to_json(), "json", theme="ansi_dark"))
        return

    summary = Table(title="SafeCode Repo Map")
    summary.add_column("Section")
    summary.add_column("Count")
    summary.add_row("Files", str(len(repo_map.files)))
    summary.add_row("Symbols", str(len(repo_map.symbols)))
    summary.add_row("Imports", str(len(repo_map.imports)))
    summary.add_row("Tests", str(len(repo_map.tests)))
    summary.add_row("Commands", str(len(repo_map.commands)))
    summary.add_row("Entrypoints", str(len(repo_map.entrypoints)))
    console.print(summary)

    if repo_map.entrypoints:
        entrypoints = Table(title="Entrypoints")
        entrypoints.add_column("Kind")
        entrypoints.add_column("Name")
        entrypoints.add_column("Target")
        for item in repo_map.entrypoints:
            location = item.path if item.line is None else f"{item.path}:{item.line}"
            entrypoints.add_row(item.kind, item.name, f"{item.target} ({location})")
        console.print(entrypoints)

    if repo_map.commands:
        commands = Table(title="Detected Commands")
        commands.add_column("Command")
        commands.add_column("Tool")
        commands.add_column("Confidence")
        for item in repo_map.commands:
            commands.add_row(item.command, item.tool, item.confidence)
        console.print(commands)


@progress_app.command("init")
def progress_init() -> None:
    """Create .sac/progress.md."""
    path = ProgressStore(Path.cwd()).ensure()
    console.print(f"Progress ready: {path}")


@progress_app.command("show")
def progress_show() -> None:
    """Show progress Markdown."""
    console.print(ProgressStore(Path.cwd()).read_text())


@progress_app.command("set")
def progress_set(goal: str, next_step: str = typer.Option("", "--next")) -> None:
    """Set a simple progress goal and optional next step."""
    state = ProgressState(goal=goal, completed=[], next_steps=[next_step] if next_step else [], blockers=[])
    ProgressStore(Path.cwd()).write(state)
    console.print("[green]Progress updated.[/green]")
