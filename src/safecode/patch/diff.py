"""Generate human-readable diffs for patch proposals."""

import difflib
from pathlib import Path

from safecode.patch.models import PatchProposal
from safecode.patch.validator import PatchValidationError


def build_unified_diff(project_root: Path, proposal: PatchProposal) -> str:
    """Return a unified diff preview without writing files."""
    diff_parts: list[str] = []
    root = project_root.resolve()

    for block in proposal.blocks:
        if block.operation != "update":
            raise PatchValidationError("v0.1.2 can build diffs for update blocks only.")
        if block.search is None or block.replace is None:
            raise PatchValidationError("Update block requires SEARCH and REPLACE for diff preview.")

        target_path = (root / block.file_path).resolve()
        try:
            relative_path = target_path.relative_to(root)
        except ValueError as exc:
            raise PatchValidationError(f"Patch path escapes project root: {block.file_path}") from exc

        old_text = target_path.read_text(encoding="utf-8")
        new_text = old_text.replace(block.search, block.replace, 1)
        diff_parts.extend(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{relative_path.as_posix()}",
                tofile=f"b/{relative_path.as_posix()}",
            )
        )

    return "".join(diff_parts)
