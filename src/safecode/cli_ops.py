import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from safecode.cli_shared import console, log_cli_error, runtime_logger, show_human_checkpoint
from safecode import __version__

from safecode.audit.logger import AuditLogger
from safecode.core.diagnostic import DiagnosticStatus
from safecode.doctor import Doctor
from safecode.eval.cases import default_cases
from safecode.eval.runner import EvalRunner
from safecode.eval.loop_runner import LoopModeEvalRunner, default_loop_fixtures
from safecode.eval.bench import EvalBenchRunner, render_bench_summary
from safecode.export.bundle import Exporter
from safecode.hooks.approvals import HookApprovalStore
from safecode.ide.bridge import pending_diff_target, selected_file_targets
from safecode.ide.manifest import render_manifest, write_manifest
from safecode.logs.runtime import RuntimeLogger
from safecode.project.rules import ProjectRules
from safecode.queue.store import QueueStore
from safecode.release.bump import bump_versions, render_bump_result
from safecode.release.check import render_release_check, run_release_check
from safecode.release.checklist import render_release_checklist
from safecode.release.changelog import generate_changelog, generate_recent_changelog, render_changelog
from safecode.release.metadata import collect_release_metadata, render_release_metadata
from safecode.release.preflight import render_release_preflight, run_release_preflight
from safecode.release.publish import PublishResult, render_publish_result, run_release_publish
from safecode.release.signoff import render_release_signoff, run_release_signoff
from safecode.release.smoke import render_smoke_results, run_smoke_tests
from safecode.release.ux import exit_code
from safecode.release.versions_sync import sync_versions_json
from safecode.report.render import ReportRenderer
from safecode.report.session_html import render_session_html

ops_app = typer.Typer()
queue_app = typer.Typer(help="Manage a tiny local task queue.")
export_app = typer.Typer(help="Export SafeCode reports.")
ide_app = typer.Typer(help="Generate IDE adapter metadata.")
release_app = typer.Typer(help="Generate release helpers.")
logs_app = typer.Typer(help="Inspect runtime logs.")
audit_app = typer.Typer(help="Inspect and verify audit logs.")
hooks_app = typer.Typer(help="Approve and inspect project hooks.")
report_app = typer.Typer(invoke_without_command=True, help="SafeCode session and audit reports.")


@ops_app.command("rules", hidden=True)
def rules(init: bool = typer.Option(False, "--init")) -> None:
    """Show or initialize SAC.md project rules."""
    rules_store = ProjectRules(Path.cwd())
    if init:
        rules_store.ensure()
    console.print(rules_store.read() or "[yellow]No SAC.md found. Run sac rules --init.[/yellow]")


@report_app.callback(invoke_without_command=True)
def report(ctx: typer.Context) -> None:
    """Render a Markdown report from recent audit events (default) or a per-session HTML report."""
    if ctx.invoked_subcommand is None:
        console.print(ReportRenderer(Path.cwd()).render_markdown())


@report_app.command("html")
def report_html(
    session: str = typer.Option(..., "--session", "-s", help="Session ID to render as HTML."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write HTML to this file instead of stdout."),
) -> None:
    """Render a self-contained HTML report for one agent session."""
    result = render_session_html(session, Path.cwd())
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.html, encoding="utf-8")
        console.print(f"Report written: {output}")
    else:
        console.print(result.html)


@export_app.command("report")
def export_report(output: Path = typer.Option(Path(".sac/reports/latest.md"), "--output", "-o")) -> None:
    """Export a Markdown report to a file."""
    path = Exporter(Path.cwd()).report(output)
    console.print(f"Report exported: {path}")


@ops_app.command("eval", hidden=True)
def eval_demo(
    mode: str = typer.Option("default", "--mode", help="Eval mode: default, loop, bench, live, real-task, dashboard, or swebench-lite."),
    update_baseline: bool = typer.Option(False, "--update-baseline", help="Overwrite bench baseline snapshots."),
    provider: str = typer.Option("anthropic", "--provider", help="LLM provider for --mode live."),
    model: str = typer.Option("", "--model", help="Model override for --mode live."),
    fixture: str = typer.Option("", "--fixture", help="Run one named fixture (live mode only)."),
    eval_suite: str = typer.Option("all", "--eval-suite", help="Live eval suite: all, regression, capability, safety, cost-perf."),
    transcripts: bool = typer.Option(False, "--transcripts", help="Write redacted live eval transcript artifacts under .sac/eval/transcripts."),
    runs: int = typer.Option(1, "--runs", help="Repeat live eval N times and print aggregate stability metrics."),
    suite: str = typer.Option("", "--suite", help="Eval suite for --mode swebench-lite (dir of task JSON files)."),
    limit: int = typer.Option(10, "--limit", help="Max tasks for --mode real-task or swebench-lite."),
    dashboard_output: Path = typer.Option(Path(".sac/eval/dashboard.md"), "--dashboard-output", help="Output path for --mode dashboard."),
) -> None:
    """Run lightweight local eval cases.

    --mode loop           runs realistic scripted agent-loop fixtures (no real LLM).
    --mode bench          runs eval bench and collects timing/hash metrics per fixture.
    --mode live           runs real coding tasks against a live provider (requires SAFECODE_LIVE_TESTS=1).
    --mode real-task      runs the built-in real-world task benchmark slice.
    --mode dashboard      renders a Markdown dashboard from latest eval reports.
    --mode swebench-lite  runs SWE-bench-Lite-compatible tasks from --suite <dir>.
    """
    if mode == "loop":
        fixtures = default_loop_fixtures()
        runner = LoopModeEvalRunner()
        results = runner.run_all(fixtures)
        table = Table(title="SafeCode Eval (loop mode)")
        table.add_column("Fixture")
        table.add_column("Passed")
        table.add_column("Stopped")
        table.add_column("Failures")
        all_passed = True
        for r in results:
            if not r.passed:
                all_passed = False
            failures = "; ".join(r.failure_reasons) if r.failure_reasons else ""
            table.add_row(r.fixture_name, "yes" if r.passed else "no", r.stopped_reason, failures)
        console.print(table)
        raise typer.Exit(code=0 if all_passed else 1)
    elif mode == "bench":
        bench_runner = EvalBenchRunner()
        summary = bench_runner.run_all(update_baseline=update_baseline)
        console.print(render_bench_summary(summary))
        raise typer.Exit(code=0 if summary.all_passed else 1)
    elif mode == "live":
        import os as _os
        from safecode.eval.live import (
            LiveEvalRunner,
            check_ratchet,
            default_live_fixtures,
            filter_live_fixtures,
            render_live_summary,
            render_repeated_summary,
            save_latest,
        )

        if not _os.environ.get("SAFECODE_LIVE_TESTS"):
            console.print(
                "[yellow]Live eval skipped: set SAFECODE_LIVE_TESTS=1 to enable.[/yellow]"
            )
            raise typer.Exit(code=0)

        all_fixtures = default_live_fixtures()
        if fixture:
            selected = [f for f in all_fixtures if f.name == fixture]
            if not selected:
                names = ", ".join(f.name for f in all_fixtures)
                console.print(f"[red]Unknown fixture {fixture!r}. Available: {names}[/red]")
                raise typer.Exit(code=1)
        else:
            try:
                selected = filter_live_fixtures(all_fixtures, eval_suite)
            except ValueError as exc:
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(code=1) from exc

        transcript_dir = Path.cwd() / ".sac" / "eval" / "transcripts" if transcripts else None
        live_runner = LiveEvalRunner(provider=provider, model=model or None, transcript_dir=transcript_dir)
        model_label = model or "default"
        console.print(
            f"Running {len(selected)} live fixture(s) with provider={provider!r}, "
            f"model={model_label!r}, suite={eval_suite!r}, runs={runs!r} …"
        )
        if runs < 1:
            console.print("[red]--runs must be >= 1[/red]")
            raise typer.Exit(code=1)
        if runs > 1:
            repeated = live_runner.run_all_repeated(selected, n_runs=runs)
            live_results = repeated[-1] if repeated else []
            console.print(render_repeated_summary(live_runner.summarize_repeated(repeated)))
        else:
            live_results = live_runner.run_all(selected)
        save_latest(live_results)
        console.print(render_live_summary(live_results))
        ratchet_failures = check_ratchet(live_results)
        if ratchet_failures:
            console.print("[red]Ratchet failures:[/red]")
            for msg in ratchet_failures:
                console.print(f"  {msg}")
            raise typer.Exit(code=1)
        all_passed = all(r.success for r in live_results)
        raise typer.Exit(code=0 if all_passed else 1)
    elif mode == "real-task":
        from safecode.eval.real_task import (
            build_real_task_manifest,
            load_default_real_tasks,
            render_real_task_report,
            run_real_task_benchmark,
            save_real_task_report,
        )

        suite_dir = Path(suite) if suite else None
        tasks = load_default_real_tasks(suite_dir)
        if not tasks:
            console.print("[yellow]No real-task benchmark tasks found.[/yellow]")
            raise typer.Exit(code=0)
        selected = tasks[:limit] if limit else tasks
        manifest = build_real_task_manifest(selected)
        report = run_real_task_benchmark(
            suite_dir=suite_dir,
            limit=limit,
            provider=provider,
        )
        console.print(render_real_task_report(report, manifest))
        out_path = save_real_task_report(report)
        console.print(f"\n[dim]Report saved: {out_path}[/dim]")
        raise typer.Exit(code=0 if report.passed == report.total else 1)
    elif mode == "dashboard":
        from safecode.eval.dashboard import build_eval_dashboard_sources, render_eval_dashboard

        sources = build_eval_dashboard_sources(Path.cwd())
        text = render_eval_dashboard(sources)
        dashboard_output.parent.mkdir(parents=True, exist_ok=True)
        dashboard_output.write_text(text, encoding="utf-8")
        console.print(text)
        console.print(f"[dim]Dashboard saved: {dashboard_output}[/dim]")
        raise typer.Exit(code=0)
    elif mode == "swebench-lite":
        from safecode.eval.swebench_adapter import (
            SWEBenchRunner, load_tasks_from_dir, render_report_text, save_report
        )
        from safecode.eval.swebench_adapter import SWEBenchLoadError
        suite_dir = Path(suite) if suite else Path.cwd() / "tests" / "eval_fixtures" / "swebench_lite"
        if not suite_dir.is_dir():
            console.print(f"[red]Suite directory not found: {suite_dir}[/red]")
            console.print("[dim]Create JSON task files in the directory or pass --suite <dir>[/dim]")
            raise typer.Exit(code=1)
        try:
            tasks = load_tasks_from_dir(suite_dir)
        except SWEBenchLoadError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc
        if not tasks:
            console.print(f"[yellow]No task files found in {suite_dir}[/yellow]")
            raise typer.Exit(code=0)
        runner = SWEBenchRunner(project_root=Path.cwd())
        report = runner.run_suite(tasks, limit=limit, provider="mock")
        console.print(render_report_text(report))
        out_path = save_report(report)
        console.print(f"\n[dim]Report saved: {out_path}[/dim]")
        raise typer.Exit(code=0 if report.passed == report.total else 1)
    else:
        results_legacy = EvalRunner(Path.cwd()).run(default_cases())
        table = Table(title="SafeCode Eval")
        table.add_column("Case")
        table.add_column("Passed")
        for result in results_legacy:
            table.add_row(result.name, "yes" if result.passed else "no")
        console.print(table)


@queue_app.command("add")
def queue_add(title: str) -> None:
    """Add a pending task to the local queue."""
    task = QueueStore(Path.cwd()).add(title)
    console.print(f"Queued task: {task.id}")


@queue_app.command("list")
def queue_list() -> None:
    """List queued tasks."""
    table = Table(title="SafeCode Queue")
    table.add_column("ID")
    table.add_column("Status")
    table.add_column("Title")
    for task in QueueStore(Path.cwd()).list():
        table.add_row(task.id, task.status, task.title)
    console.print(table)


@queue_app.command("complete-next")
def queue_complete_next() -> None:
    """Mark the next pending task as completed."""
    task = QueueStore(Path.cwd()).complete_next()
    console.print(f"Completed task: {task.id}" if task else "[yellow]No pending tasks.[/yellow]")


@ide_app.command("manifest")
def ide_manifest(write: bool = typer.Option(False, "--write")) -> None:
    """Show or write an IDE command manifest."""
    if write:
        path = write_manifest(Path.cwd())
        console.print(f"IDE manifest written: {path}")
    else:
        console.print(Syntax(render_manifest(), "json", theme="ansi_dark"))


@ide_app.command("open-diff")
def ide_open_diff() -> None:
    """Print the materialized pending diff target for an IDE bridge."""
    try:
        target = pending_diff_target(Path.cwd())
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"{target.uri}\n{target.path}")


@ide_app.command("open-files")
def ide_open_files(query: str, limit: int = typer.Option(5, "--limit", min=1)) -> None:
    """Print selected safe file targets for an IDE bridge."""
    targets = selected_file_targets(Path.cwd(), query, limit=limit)
    if not targets:
        console.print("[yellow]No selected files found.[/yellow]")
        return
    table = Table(title="IDE Open Targets")
    table.add_column("Label")
    table.add_column("URI")
    table.add_column("Path")
    for target in targets:
        table.add_row(target.label, target.uri, str(target.path))
    console.print(table)
    for target in targets:
        console.print(f"{target.uri}\n{target.path}")


@release_app.command("checklist", hidden=True, help="[advanced] Render a release checklist. Prefer: bump -> pytest -> tag -> preflight.")
def release_checklist(
    version: str,
    help_note: Optional[str] = typer.Option(None, "--help-note", help="[advanced] Planning helper; prefer sac release preflight."),
) -> None:
    """[advanced] Render a release checklist. Prefer: bump -> pytest -> tag -> preflight."""
    console.print(render_release_checklist(version))


@release_app.command("check", hidden=True, help="[advanced] Report version consistency and working-tree state. Prefer: sac release preflight.")
def release_check(
    help_note: Optional[str] = typer.Option(None, "--help-note", help="[advanced] Prefer sac release preflight."),
) -> None:
    """[advanced] Report version consistency and working-tree state. Prefer: sac release preflight."""
    result = run_release_check(Path.cwd())
    console.print(render_release_check(result))
    if not result.ok:
        raise typer.Exit(code=exit_code(result.ok))


@release_app.command("smoke", hidden=True, help="[advanced] Run a fast release smoke test (import, version, policy). Prefer: sac release preflight.")
def release_smoke(
    help_note: Optional[str] = typer.Option(None, "--help-note", help="[advanced] Prefer sac release preflight."),
) -> None:
    """[advanced] Run a fast release smoke test (import, version, policy). Prefer: sac release preflight."""
    result = run_smoke_tests()
    console.print(render_smoke_results(result))
    if not result.ok:
        raise typer.Exit(code=exit_code(result.ok))


@release_app.command("bump")
def release_bump(
    version: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing files."),
) -> None:
    """Update all canonical version locations to VERSION (X.Y.Z)."""
    result = bump_versions(version, project_root=Path.cwd(), dry_run=dry_run)
    console.print(render_bump_result(result))
    if not result.ok:
        raise typer.Exit(code=exit_code(result.ok))


@release_app.command("meta", hidden=True, help="[advanced] Show release metadata index: version, tag, notes, and baseline consistency.")
def release_meta(
    help_note: Optional[str] = typer.Option(None, "--help-note", help="[advanced] Metadata helper; prefer sac release preflight."),
) -> None:
    """[advanced] Show release metadata index: version, tag, notes, and baseline consistency."""
    meta = collect_release_metadata(Path.cwd())
    console.print(render_release_metadata(meta))
    if not meta.ok:
        raise typer.Exit(code=exit_code(meta.ok))


@release_app.command("preflight")
def release_preflight(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Run the fast local release gate: check, smoke, metadata, and docs."""
    from safecode.cli_shared_json import CLIJSONResponse, render_json as _render_json

    result = run_release_preflight(Path.cwd())
    if json_output:
        gov = result.versions_governance
        print(_render_json(CLIJSONResponse(
            command="release preflight",
            status="pass" if result.ok else "fail",
            data={
                "ok": result.ok,
                "release_check": result.release_check.ok,
                "smoke": result.smoke.ok,
                "metadata": result.metadata.ok,
                "docs": result.docs.ok,
                "versions_governance": gov.ok if gov is not None else True,
            },
        )))
        if not result.ok:
            raise typer.Exit(code=exit_code(result.ok))
        return
    console.print(render_release_preflight(result))
    if not result.ok:
        raise typer.Exit(code=exit_code(result.ok))


@release_app.command("publish")
def release_publish(
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Show planned steps without executing (default: dry-run)."),
    sign: bool = typer.Option(False, "--sign", help="Sign artifacts with detached cosign or gpg signature (fails closed if tooling is missing)."),
    repository: str = typer.Option("pypi", "--repository", help="Target repository: 'pypi' (default) or 'test-pypi' for rehearsal."),
    update_brew: bool = typer.Option(False, "--update-brew", help="After a real publish, regenerate Formula/safecode-agent.rb via scripts/update-brew-formula.sh (v5.5.1)."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Build, sign (optional), and upload a release to PyPI or TestPyPI.

    Dry-run is the safe default. Real publish requires a clean matching git tag and SAFECODE_PUBLISH=1.
    Use --repository test-pypi for a TestPyPI rehearsal (still requires SAFECODE_PUBLISH=1).
    Use --update-brew to regenerate the Homebrew formula after a successful real publish.
    """
    result = run_release_publish(Path.cwd(), dry_run=dry_run, sign=sign, repository=repository)

    # v5.5.1: regenerate Homebrew formula after a successful real publish to PyPI.
    brew_message: str | None = None
    if result.ok and not dry_run and update_brew and repository == "pypi":
        brew_message = _run_update_brew_formula(Path.cwd())

    if json_output:
        from safecode.cli_shared_json import CLIJSONResponse, render_json
        data: dict = {
            "dry_run": result.dry_run,
            "repository": result.repository,
            "steps": list(result.steps),
            "errors": list(result.errors),
        }
        if brew_message is not None:
            data["brew_formula_update"] = brew_message
        resp = CLIJSONResponse(
            command="release publish",
            status="ok" if result.ok else "error",
            data=data,
        )
        console.print(render_json(resp))
    else:
        console.print(render_publish_result(result))
        if brew_message is not None:
            console.print(f"[green]Homebrew formula:[/green] {brew_message}")
    if not result.ok:
        raise typer.Exit(code=exit_code(result.ok))


def _run_update_brew_formula(project_root: Path) -> str:
    """Run scripts/update-brew-formula.sh with the current version; return status message."""
    import subprocess
    import re

    try:
        from safecode import __version__
        version = __version__
    except Exception:
        return "could not determine version; skipping Homebrew formula update"

    script = project_root / "scripts" / "update-brew-formula.sh"
    if not script.exists():
        return "scripts/update-brew-formula.sh not found; skipping"

    # Try to find the wheel sha256 from dist/.
    dist_dir = project_root / "dist"
    sha256 = ""
    if dist_dir.exists():
        import hashlib
        for artifact in sorted(dist_dir.glob("*.whl")):
            sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
            break

    try:
        proc = subprocess.run(
            ["bash", str(script), version, sha256 or "UNKNOWN"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=30,
        )
        if proc.returncode == 0:
            return f"Formula/safecode-agent.rb updated for v{version}"
        return f"formula update script failed (exit {proc.returncode})"
    except Exception as exc:
        return f"formula update failed: {type(exc).__name__}"


@release_app.command("changelog")
def release_changelog(
    from_version: Optional[str] = typer.Option(None, "--from", help="First version to include, e.g. 2.6.10."),
    to_version: Optional[str] = typer.Option(None, "--to", help="Last version to include, e.g. 2.6.15."),
    recent: Optional[int] = typer.Option(None, "--recent", min=1, help="Include the latest N version-note versions."),
) -> None:
    """Print a Markdown changelog from local version-note files."""
    notes_dir = Path.cwd() / "docs" / "version-notes"
    if recent is not None:
        result = generate_recent_changelog(recent, version_notes_dir=notes_dir)
    elif from_version is not None and to_version is not None:
        result = generate_changelog(from_version, to_version, version_notes_dir=notes_dir)
    else:
        console.print("[red]Provide either --recent N or both --from and --to.[/red]")
        raise typer.Exit(code=1)
    console.print(render_changelog(result))
    if not result.ok:
        raise typer.Exit(code=exit_code(result.ok))


@release_app.command("signoff", hidden=True, help="[internal] Run the final local release signoff. Not required for the standard release flow.")
def release_signoff(
    help_note: Optional[str] = typer.Option(None, "--help-note", help="[internal] Not required for the standard release flow."),
) -> None:
    """[internal] Run the final local release signoff. Not required for the standard release flow."""
    warnings.warn(
        "sac release signoff is deprecated. Use `sac release preflight` instead.",
        RuntimeWarning,
        stacklevel=2,
    )
    result = run_release_signoff(Path.cwd())
    console.print(render_release_signoff(result))
    if not result.ok:
        raise typer.Exit(code=exit_code(result.ok))


@release_app.command("sync-versions-json")
def release_sync_versions_json(
    dry_run: bool = typer.Option(False, "--dry-run", help="Report without writing."),
) -> None:
    """Sync .claude/versions.json latest_tags and current_implemented_tag from git tags."""
    result = sync_versions_json(project_root=Path.cwd(), dry_run=dry_run)
    status = "[green]OK[/green]" if result.ok else "[red]FAIL[/red]"
    console.print(f"{status} {result.message}")
    if not result.ok:
        raise typer.Exit(code=1)


@ops_app.command("doctor")
def doctor(
    release: bool = typer.Option(False, "--release", help="Include release tag/docs/preflight diagnostics."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
    live: bool = typer.Option(False, "--live", help="Attempt a lightweight connectivity ping to the provider (opt-in)."),
) -> None:
    """Check local install and project environment."""
    from safecode.cli_shared_json import CLIJSONResponse, render_json

    diagnostics = Doctor(Path.cwd()).run_diagnostics(release=release, live=live)
    if json_output:
        all_passed = all(d.status == DiagnosticStatus.PASS for d in diagnostics)
        print(render_json(CLIJSONResponse(
            command="doctor",
            status="pass" if all_passed else "fail",
            data={"checks": [d.as_dict() for d in diagnostics]},
        )))
        return

    # Top-line verdict
    failed_count = sum(1 for d in diagnostics if d.status == DiagnosticStatus.FAIL)
    warn_count = sum(1 for d in diagnostics if d.status == DiagnosticStatus.WARN)
    if failed_count == 0 and warn_count == 0:
        console.print("[bold green]Overall: READY[/bold green]")
    else:
        parts = []
        if failed_count:
            parts.append(f"{failed_count} issue(s)")
        if warn_count:
            parts.append(f"{warn_count} warning(s)")
        console.print(f"[bold red]Overall: NEEDS SETUP — {', '.join(parts)}[/bold red]")
    console.print("")

    table = Table(title="SafeCode Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    table.add_column("Next")
    _status_labels = {
        DiagnosticStatus.PASS: "[green]PASS[/green]",
        DiagnosticStatus.FAIL: "[red]FAIL[/red]",
        DiagnosticStatus.WARN: "[yellow]WARN[/yellow]",
        DiagnosticStatus.SKIP: "[dim]SKIP[/dim]",
    }
    for d in diagnostics:
        status_str = _status_labels.get(d.status, d.status.value)
        next_hint = d.hints[0] if d.hints else ""
        table.add_row(d.name, status_str, d.message, next_hint)
    console.print(table)


_V5_STABLE_CONTRACTS = [
    "read_file",
    "list_files",
    "search_files",
    "grep_files",
    "edit_file",
    "write_file",
    "run_command",
    "tool_call_read",
    "tool_call_write",
    "tool_call_command",
    "write_tool_checkpoint_rollback",
    "sac_shell_loop",
]

_STABLE_CONTRACTS = _V5_STABLE_CONTRACTS + [
    "sandbox_execution_lifecycle",
    "trust_mode_schema",
    "session_rollback",
    "github_pr_workflow",
    "project_memory_store_shape",
    "search_symbol",
    "model_context_budget_profile",
]


@ops_app.command("version", hidden=True)
def version(
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Show SafeCode package version and update hints."""
    from safecode.cli_shared_json import CLIJSONResponse, render_json

    if json_output:
        print(render_json(CLIJSONResponse(
            command="version",
            status="success",
            data={"version": __version__, "stable_contracts": _STABLE_CONTRACTS},
        )))
        return
    console.print(f"SafeCode Agent {__version__}")
    console.print("Update source checkout: git pull --ff-only && python -m pytest -q")


@logs_app.command("show")
def logs_show(
    limit: int = typer.Option(20, "--limit", "-n"),
    level: Optional[str] = typer.Option(None, "--level"),
    traceback_: bool = typer.Option(False, "--traceback", help="Show traceback text."),
) -> None:
    """Show recent structured runtime logs."""
    events = RuntimeLogger(Path.cwd()).read_recent(limit=limit, level=level)
    if not events:
        console.print("[yellow]No runtime logs found.[/yellow]")
        return

    table = Table(title="SafeCode Runtime Logs")
    table.add_column("Time")
    table.add_column("Level")
    table.add_column("Component")
    table.add_column("Message")
    table.add_column("Error")
    table.add_column("Details")
    for event in events:
        details = ", ".join(f"{key}={value}" for key, value in event.details.items())
        table.add_row(
            event.timestamp,
            event.level,
            event.component,
            event.message,
            event.error_type or "",
            details,
        )
        if traceback_ and event.traceback:
            table.add_row("", "", "", event.traceback, "", "")
    console.print(table)


@audit_app.command("verify")
def audit_verify() -> None:
    """Verify audit log hash-chain integrity."""
    ok, message = AuditLogger(Path.cwd()).verify_integrity()
    color = "green" if ok else "red"
    console.print(f"[{color}]{message}[/{color}]")
    if not ok:
        raise typer.Exit(code=1)


@audit_app.command("query")
def audit_query(
    event_type: Optional[str] = typer.Option(None, "--type", help="[EXPERIMENTAL] Filter by audit event type."),
    since: Optional[str] = typer.Option(None, "--since", help="[EXPERIMENTAL] ISO date/datetime lower bound."),
    task: Optional[str] = typer.Option(None, "--task", help="[EXPERIMENTAL] Filter by metadata.task_id."),
    limit: int = typer.Option(20, "--limit", min=1),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Read-only audit event query with integrity verification."""
    from safecode.cli_shared_json import CLIJSONResponse, render_json
    from safecode.context.redactor import redact_secrets

    logger = AuditLogger(Path.cwd())
    ok, message = logger.verify_integrity()
    if not ok:
        if json_output:
            print(render_json(CLIJSONResponse(command="audit query", status="error", error=message)))
        else:
            console.print(f"[red]{message}[/red]")
        raise typer.Exit(code=1)

    try:
        since_dt = _parse_since(since) if since else None
    except ValueError as exc:
        if json_output:
            print(render_json(CLIJSONResponse(command="audit query", status="error", error=str(exc))))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    events = logger.iter_events()
    if event_type is not None:
        events = [event for event in events if event.type == event_type]
    if task is not None:
        events = [event for event in events if event.metadata.get("task_id") == task]
    if since_dt is not None:
        events = [event for event in events if _event_datetime(event.timestamp) >= since_dt]
    events = events[-limit:]
    data_events = [_redacted_audit_event(event, redact=redact_secrets) for event in events]
    data = {"integrity": message, "events": data_events, "count": len(data_events)}
    if json_output:
        print(render_json(CLIJSONResponse(command="audit query", status="success", data=data)))
        return

    table = Table(title="SafeCode Audit Query [EXPERIMENTAL]")
    table.add_column("Time")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Task")
    table.add_column("Message")
    for event in data_events:
        table.add_row(
            str(event["timestamp"]),
            str(event["type"]),
            str(event["status"]),
            str(event["metadata"].get("task_id", "")),
            str(event.get("message") or event.get("error") or ""),
        )
    console.print(table)


def _parse_since(value: str) -> datetime:
    raw = value.strip()
    try:
        if len(raw) == 10:
            return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--since must be an ISO date or datetime.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _event_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _redacted_audit_event(event, *, redact) -> dict:
    data = event.model_dump(mode="json")
    for field in ("message", "error", "command"):
        if data.get(field):
            data[field] = redact(str(data[field]))
    data["files"] = [redact(str(path)) for path in data.get("files", [])]
    data["metadata"] = {str(key): redact(str(value)) for key, value in data.get("metadata", {}).items()}
    return data


@hooks_app.command("approve")
def hooks_approve(
    command: str,
    hook: str = typer.Option("after_apply", "--hook"),
    ttl_hours: int = typer.Option(24, "--ttl-hours", min=1),
) -> None:
    """Approve one exact hook command."""
    approval = HookApprovalStore(Path.cwd()).approve(hook, command, ttl_hours=ttl_hours)
    console.print(f"[green]Hook approved:[/green] {approval.command_hash}")
    console.print(f"Expires: {approval.expires_at}")


@hooks_app.command("list")
def hooks_list() -> None:
    """List stored hook approvals."""
    approvals = HookApprovalStore(Path.cwd()).list()
    table = Table(title="SafeCode Hook Approvals")
    table.add_column("Hook")
    table.add_column("Command")
    table.add_column("Approved At")
    table.add_column("Expires At")
    table.add_column("Hash")
    for approval in approvals:
        table.add_row(approval.hook_name, approval.command, approval.approved_at, approval.expires_at, approval.command_hash[:12])
    console.print(table if approvals else "[yellow]No hook approvals found.[/yellow]")
