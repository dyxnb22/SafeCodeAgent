"""Command line entrypoint for SafeCode Agent."""

import typer

from safecode.cli_agent import agent_app
from safecode.cli_context import context_app
from safecode.cli_core import core_app
from safecode.cli_mcp import mcp_app, mcp_discard
from safecode.cli_ops import audit_app, export_app, hooks_app, ide_app, logs_app, ops_app, queue_app, release_app
from safecode.cli_project import config_app, index_app, progress_app, skills_app, tools_app
from safecode.cli_sandbox import sandbox_app
from safecode.cli_subagent import subagent_app
from safecode.cli_test_demo import demo_app, test_app
from safecode.cli_tui import tui_app

app = typer.Typer(
    name="sac",
    help="SafeCode Agent: safety-first terminal coding assistant.",
    no_args_is_help=True,
)


@app.callback()
def callback() -> None:
    """Keep Typer in multi-command mode."""


# Core commands stay at the root for backward compatibility.
for command in core_app.registered_commands:
    app.registered_commands.append(command)
for command in ops_app.registered_commands:
    app.registered_commands.append(command)

app.add_typer(context_app, name="context")
app.add_typer(config_app, name="config")
app.add_typer(skills_app, name="skills")
app.add_typer(tools_app, name="tools")
app.add_typer(index_app, name="index")
app.add_typer(progress_app, name="progress")
app.add_typer(mcp_app, name="mcp")
app.add_typer(subagent_app, name="subagent")
app.add_typer(queue_app, name="queue")
app.add_typer(export_app, name="export")
app.add_typer(ide_app, name="ide")
app.add_typer(release_app, name="release")
app.add_typer(logs_app, name="logs")
app.add_typer(audit_app, name="audit")
app.add_typer(hooks_app, name="hooks")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(agent_app, name="agent")
app.add_typer(test_app, name="test")
app.add_typer(demo_app, name="demo")
app.add_typer(tui_app, name="tui")


def main() -> None:
    """Console script entrypoint."""
    app()


if __name__ == "__main__":
    main()
