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
        output_dir: Path | None = typer.Option(
            None,
            "--output-dir",
            help="Persistent demo workspace; writes .sac state under this directory.",
        ),
        keep_runs: bool = typer.Option(
            False,
            "--keep-runs",
            help="Keep the temporary demo workspace after the run completes.",
        ),
        show_run_metadata: bool = typer.Option(
            False,
            "--show-run-metadata",
            help="Include volatile run metadata such as raw audit_chain_head.",
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
        transcript = run_pr_review_offline_demo(
            project_root,
            workspace_root=output_dir,
            keep_runs=keep_runs or output_dir is not None,
            show_run_metadata=show_run_metadata,
        )
        typer.echo(transcript, nl=False)
        raise typer.Exit(code=0)
