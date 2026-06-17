"""Generate approval-gated test patches for a target function or file."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from safecode.cli_shared import console
from safecode.cli_shared_json import CLIJSONResponse, render_json

testgen_app = typer.Typer(help="[EXPERIMENTAL] Generate tests as pending patches.")


@testgen_app.command("generate")
def test_generate(
    target: str = typer.Argument(..., help="Target file or file.py::symbol."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Suggested test file path."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Generate tests for TARGET and save them as a pending patch."""
    from safecode.agent.orchestrator import AgentOrchestrator

    project_root = Path.cwd()

    try:
        prompt, metadata = _build_test_prompt(project_root, target, output)
    except ValueError as exc:
        if json_output:
            print(render_json(CLIJSONResponse(command="test-gen", status="error", error=str(exc))))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    try:
        result = AgentOrchestrator(project_root).edit(prompt)
    except Exception as exc:
        if json_output:
            print(render_json(CLIJSONResponse(command="test-gen", status="error", error=str(exc))))
        else:
            console.print(f"[red]Test generation failed: {exc}[/red]")
        raise typer.Exit(1)

    data = {
        **metadata,
        "patch_id": result.proposal.id,
        "pending_patch_path": str(result.pending_patch_path),
        "files": [block.file_path.as_posix() for block in result.proposal.blocks],
    }
    if json_output:
        print(render_json(CLIJSONResponse(command="test-gen", status="pending", data=data)))
        return
    console.print(f"[green]Test patch proposed:[/green] {result.pending_patch_path}")
    console.print("[dim]Review with 'sac apply'.[/dim]")


def _build_test_prompt(project_root: Path, target: str, output: str | None) -> tuple[str, dict]:
    target_file, symbol = _resolve_target(project_root, target)
    rel_file = target_file.relative_to(project_root).as_posix()
    implementation = _read_limited(target_file, max_chars=6000)
    existing_tests = _collect_existing_tests(project_root, symbol or target_file.stem)
    output_hint = output or _default_test_output(rel_file)

    prompt = (
        f"Generate focused tests for target `{target}`.\n\n"
        f"Implementation file: {rel_file}\n"
        f"Symbol: {symbol or '(whole file)'}\n"
        f"Suggested test file: {output_hint}\n\n"
        "Implementation excerpt:\n"
        f"```python\n{implementation}\n```\n\n"
        "Existing tests excerpt (avoid duplicates):\n"
        f"```python\n{existing_tests or '# no existing tests found'}\n```\n\n"
        "Create or update tests only. Include at least three meaningful cases when possible, "
        "including edge cases and one regression-style assertion. Save the result as a pending patch; "
        "do not apply it automatically."
    )
    return prompt, {"target": target, "target_file": rel_file, "symbol": symbol, "suggested_output": output_hint}


def _resolve_target(project_root: Path, target: str) -> tuple[Path, str | None]:
    if "::" in target:
        file_part, symbol = target.split("::", 1)
        if not file_part or not symbol:
            raise ValueError("Target must be file.py::symbol or a file path.")
        path = (project_root / file_part).resolve()
        _validate_inside(project_root, path)
        if not path.is_file():
            raise ValueError(f"Target file not found: {file_part}")
        return path, symbol

    path = (project_root / target).resolve()
    _validate_inside(project_root, path)
    if path.is_file():
        return path, None

    from safecode.index.python_symbols import PythonSymbolIndexer

    matches = [sym for sym in PythonSymbolIndexer(project_root).index() if sym.name == target]
    if not matches:
        raise ValueError(f"Target not found: {target}")
    if len(matches) > 1:
        choices = ", ".join(f"{sym.path}::{sym.name}" for sym in matches[:10])
        raise ValueError(f"Multiple symbols named {target!r}; use file.py::symbol. Choices: {choices}")
    match = matches[0]
    return (project_root / match.path).resolve(), match.name


def _validate_inside(project_root: Path, path: Path) -> None:
    try:
        path.relative_to(project_root.resolve())
    except ValueError as exc:
        raise ValueError("Target path is outside project root.") from exc


def _read_limited(path: Path, *, max_chars: int) -> str:
    return path.read_text(encoding="utf-8", errors="replace")[:max_chars]


def _collect_existing_tests(project_root: Path, hint: str) -> str:
    chunks: list[str] = []
    for path in sorted(project_root.rglob("test_*.py"))[:8]:
        if ".venv" in path.parts or ".sac" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if hint in text or len(chunks) < 2:
            rel = path.relative_to(project_root).as_posix()
            chunks.append(f"# {rel}\n{text[:2000]}")
        if len("".join(chunks)) > 5000:
            break
    return "\n\n".join(chunks)[:5000]


def _default_test_output(rel_file: str) -> str:
    stem = Path(rel_file).stem
    return f"tests/test_{stem}.py"
