"""sac rename — safe symbol rename with reference-aware patch generation (v6.9.1).

Finds all references to a Python function or class, generates a single
multi-file PatchProposal with word-boundary replacements, and routes it
through the standard diff → confirm → checkpoint → apply flow.

Safety:
- Never modifies string literals that happen to contain the name.
- The generated patch goes through PatchValidator before being shown.
- All file writes go through the existing checkpointed apply path.
- path traversal is blocked via project root boundary check.
"""

from __future__ import annotations

import re
import tokenize
from io import StringIO
from pathlib import Path
from typing import Optional

import typer

from safecode.cli_shared import console

refactor_app = typer.Typer(help="[EXPERIMENTAL] Safe symbol refactoring tools.")


# ---------------------------------------------------------------------------
# Core rename logic (importable for testing)
# ---------------------------------------------------------------------------

_WORD_RE_TEMPLATE = r"\b{symbol}\b"


def _replace_symbol_in_line(line: str, old: str, new: str) -> str:
    """Replace *old* with *new* in Python NAME tokens on one line."""
    return _replace_symbol_in_source(line, old, new)


def _replace_symbol_in_source(
    source: str,
    old: str,
    new: str,
    *,
    target_lines: set[int] | None = None,
) -> str:
    """Replace Python NAME tokens, never strings/comments/docstrings.

    ``target_lines`` is 1-based relative to ``source``. When provided, only
    tokens starting on those lines are changed; context lines remain byte-for-
    byte identical for safer SEARCH/REPLACE blocks.
    """
    try:
        tokens = []
        reader = StringIO(source).readline
        for tok in tokenize.generate_tokens(reader):
            if (
                tok.type == tokenize.NAME
                and tok.string == old
                and (target_lines is None or tok.start[0] in target_lines)
            ):
                tok = tok._replace(string=new)
            tokens.append(tok)
        return tokenize.untokenize(tokens)
    except (tokenize.TokenError, IndentationError):
        return source


def build_rename_patch(
    old_name: str,
    new_name: str,
    refs: list[dict],
    project_root: Path,
) -> list[dict]:
    """Build SEARCH/REPLACE patch blocks for each file containing *old_name*.

    Returns a list of dicts suitable for constructing PatchBlock objects:
    ``[{file_path, search, replace}]``.

    Each block covers the minimal contiguous range of lines changed in
    that file. Files with no changed lines are skipped.
    """
    from collections import defaultdict

    # Group references by file, collect line numbers
    file_lines: dict[str, set[int]] = defaultdict(set)
    for ref in refs:
        f = ref.get("file", "")
        ln = ref.get("line", 0)
        if f and ln:
            file_lines[f].add(ln)

    blocks = []
    pattern = re.compile(_WORD_RE_TEMPLATE.format(symbol=re.escape(old_name)))

    for rel_path, touched_lines in sorted(file_lines.items()):
        abs_path = project_root / rel_path
        if not abs_path.is_file():
            continue
        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = content.splitlines(keepends=True)
        # Expand to include context: 1 line before/after each changed line
        expanded: set[int] = set()
        for ln in touched_lines:
            idx = ln - 1  # 0-based
            expanded.update(range(max(0, idx - 1), min(len(lines), idx + 2)))

        if not expanded:
            continue

        # Find contiguous groups
        groups: list[list[int]] = []
        for idx in sorted(expanded):
            if groups and idx == groups[-1][-1] + 1:
                groups[-1].append(idx)
            else:
                groups.append([idx])

        for group in groups:
            search_chunk = "".join(lines[i] for i in group)
            # Check if the symbol actually appears in this group
            if not pattern.search(search_chunk):
                continue
            touched_in_group = {i - group[0] + 1 for i in group if (i + 1) in touched_lines}
            replace_chunk = _replace_symbol_in_source(
                search_chunk,
                old_name,
                new_name,
                target_lines=touched_in_group,
            )
            if replace_chunk == search_chunk:
                continue
            blocks.append({
                "file_path": rel_path,
                "search": search_chunk,
                "replace": replace_chunk,
            })

    return blocks


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@refactor_app.command("rename")
def rename(
    old_name: str = typer.Argument(..., help="Current symbol name (function or class)."),
    new_name: str = typer.Argument(..., help="New symbol name."),
    file: Optional[str] = typer.Option(None, "--file", "-f",
                                        help="Restrict definition search to this file."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without creating a patch."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """[EXPERIMENTAL] Rename a Python symbol across the project.

    Finds all references to OLD_NAME using semantic analysis (jedi if available,
    otherwise AST+regex), generates a single multi-file patch with word-boundary
    replacements, and routes it through the standard sac apply flow.

    String literals containing the symbol are NOT renamed.
    """
    from safecode.cli_shared_json import CLIJSONResponse, render_json
    from safecode.agent.find_references_tool import AmbiguousSymbolError, find_references
    from safecode.patch.models import PatchBlock, PatchProposal
    from safecode.patch.validator import PatchValidator
    from safecode.patch.diff import build_unified_diff
    from safecode.agent.orchestrator import AgentOrchestrator
    from safecode.utils.time import utc_now_iso
    import uuid

    project_root = Path.cwd()

    def _err(msg: str, code: int = 1) -> None:
        if json_output:
            print(render_json(CLIJSONResponse(command="rename", status="error", error=msg)))
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code)

    # Validate names
    if not old_name.isidentifier():
        _err(f"Invalid symbol name: {old_name!r}")
    if not new_name.isidentifier():
        _err(f"Invalid new name: {new_name!r}")
    if old_name == new_name:
        _err("Old and new names are identical.")

    # Validate optional file hint
    if file is not None:
        try:
            resolved = (project_root / file).resolve(strict=False)
            resolved.relative_to(project_root.resolve())
        except ValueError:
            _err("--file path is outside the project root.")

    if not json_output:
        console.print(f"[dim]Searching references to '{old_name}'...[/dim]")
    try:
        refs = find_references(old_name, project_root, file=file)
    except AmbiguousSymbolError as exc:
        _err(str(exc))

    if not refs:
        if json_output:
            print(render_json(CLIJSONResponse(command="rename", status="success",
                                               data={"refs_found": 0, "blocks": 0})))
        else:
            console.print(f"[yellow]No references found for '{old_name}'.[/yellow]")
        return

    if not json_output:
        console.print(f"[dim]Found {len(refs)} reference(s) across "
                      f"{len({r['file'] for r in refs})} file(s).[/dim]")

    # Build patch blocks
    blocks_data = build_rename_patch(old_name, new_name, refs, project_root)

    if not blocks_data:
        if json_output:
            print(render_json(CLIJSONResponse(command="rename", status="success",
                                               data={"refs_found": len(refs), "blocks": 0,
                                                     "message": "No lines required renaming."})))
        else:
            console.print("[yellow]No lines required renaming (all occurrences are inside strings?).[/yellow]")
        return

    if dry_run:
        if json_output:
            print(render_json(CLIJSONResponse(command="rename", status="success",
                                               data={"dry_run": True, "refs_found": len(refs),
                                                     "blocks": len(blocks_data),
                                                     "files": list({b["file_path"] for b in blocks_data})})))
        else:
            console.print(f"[bold]Would rename {len(blocks_data)} block(s) across "
                          f"{len({b['file_path'] for b in blocks_data})} file(s):[/bold]")
            for b in blocks_data:
                console.print(f"  {b['file_path']}")
        return

    # Build PatchProposal
    patch_blocks = [
        PatchBlock(
            operation="update",
            file_path=Path(b["file_path"]),
            search=b["search"],
            replace=b["replace"],
        )
        for b in blocks_data
    ]
    proposal = PatchProposal(
        id=uuid.uuid4().hex[:12],
        task=f"rename {old_name!r} → {new_name!r}",
        blocks=patch_blocks,
        created_at=utc_now_iso(),
        model="refactor",
    )

    # Validate before showing
    try:
        PatchValidator(project_root).validate(proposal)
    except Exception as exc:
        _err(f"Patch validation failed: {exc}")

    # Show unified diff
    try:
        diff_text = build_unified_diff(project_root, proposal)
    except Exception:
        diff_text = "(diff unavailable)"

    if json_output:
        try:
            AgentOrchestrator(project_root)._save_pending_patch(proposal)
        except Exception as exc:
            _err(f"Failed to save pending patch: {exc}")
        print(render_json(CLIJSONResponse(
            command="rename",
            status="pending",
            data={
                "old_name": old_name,
                "new_name": new_name,
                "refs_found": len(refs),
                "blocks": len(blocks_data),
                "files": list({b["file_path"] for b in blocks_data}),
                "patch_id": proposal.id,
            }
        )))
        return

    # TTY: show diff and confirm
    from rich.syntax import Syntax
    console.print(Syntax(diff_text, "diff", theme="ansi_dark"))
    console.print()
    console.print(f"[bold]Rename:[/bold] '{old_name}' → '{new_name}'  "
                  f"({len(blocks_data)} block(s) in {len({b['file_path'] for b in blocks_data})} file(s))")

    try:
        confirm = typer.confirm("Apply this rename patch?", default=False)
    except Exception:
        confirm = False

    if not confirm:
        console.print("[yellow]Rename cancelled.[/yellow]")
        return

    try:
        apply_result = AgentOrchestrator(project_root).apply(proposal)
        console.print(
            f"[green]Renamed:[/green] '{old_name}' → '{new_name}'  "
            f"checkpoint={apply_result.checkpoint.checkpoint_id}  "
            f"files={', '.join(apply_result.files)}"
        )
        console.print("[dim]Run 'sac rollback --last' to undo.[/dim]")
    except Exception as exc:
        _err(f"Apply failed: {exc}")
