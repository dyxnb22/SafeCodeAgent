"""Enterprise portfolio demo CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from safecode.enterprise.demo.pr_review import DEMO_NAME, run_pr_review_offline_demo

ENTERPRISE_DEMOS = (DEMO_NAME,)


def register(demo_app: typer.Typer) -> None:
    """Attach enterprise portfolio demos to the shared ``sac demo`` group."""

    @demo_app.callback(invoke_without_command=True)
    def demo_callback(
        ctx: typer.Context,
        list_demos: bool = typer.Option(False, "--list", help="List enterprise demos."),
    ) -> None:
        if list_demos:
            for name in ENTERPRISE_DEMOS:
                typer.echo(name)
            raise typer.Exit(code=0)
        if ctx.invoked_subcommand is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(code=0)

    @demo_app.command("pr-review")
    def pr_review_demo(
        offline: bool = typer.Option(
            False,
            "--offline",
            help="Run with offline fixtures only (no network or live providers).",
        ),
        root: Path = typer.Option(
            None,
            "--root",
            help="Project root containing examples/enterprise fixtures.",
        ),
    ) -> None:
        """Run the offline PR security review portfolio demo."""
        if not offline:
            typer.echo("Only --offline mode is supported for pr-review.", err=True)
            raise typer.Exit(code=1)
        project_root = (root or Path.cwd()).resolve()
        fixture = project_root / "examples" / "enterprise" / "fixtures" / "pr_sql_injection"
        if not fixture.is_dir():
            typer.echo(
                "Missing examples/enterprise/fixtures/pr_sql_injection; "
                "run from the repository root or pass --root.",
                err=True,
            )
            raise typer.Exit(code=1)
        transcript = run_pr_review_offline_demo(project_root)
        typer.echo(transcript, nl=False)
        raise typer.Exit(code=0)
