"""CLI surface for the LocalAPI JSON-RPC bridge (experimental)."""

from pathlib import Path

import typer

api_app = typer.Typer(help="[EXPERIMENTAL] Local API bridge commands.")


@api_app.command("jsonrpc")
def api_jsonrpc(
    project_root: str = typer.Option(
        "", "--project-root", help="Project root (defaults to CWD)."
    ),
) -> None:
    """[EXPERIMENTAL] Run the SafeCodeLocalAPI stdio JSON-RPC server.

    Reads newline-delimited JSON-RPC 2.0 requests from stdin and writes
    responses to stdout. Supports: ask, report, edit, apply.

    This command is designed to be launched as a subprocess by an IDE
    extension (e.g., VS Code). It is not a stable public contract.
    """
    from safecode.api.jsonrpc import run_server

    root = Path(project_root) if project_root else Path.cwd()
    run_server(root)
