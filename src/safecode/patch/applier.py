"""Apply validated patch proposals to files."""

from pathlib import Path

from safecode.patch.models import PatchProposal
from safecode.patch.validator import PatchValidationError


class PatchApplier:
    """Write patch changes after user approval and checkpoint creation."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def apply(self, proposal: PatchProposal) -> None:
        """Apply a validated patch proposal."""
        for block in proposal.blocks:
            if block.operation != "update":
                raise PatchValidationError("v0.1.3 can apply update blocks only.")
            if block.search is None or block.replace is None:
                raise PatchValidationError("Update block requires SEARCH and REPLACE.")

            target_path = (self.project_root / block.file_path).resolve()
            try:
                target_path.relative_to(self.project_root)
            except ValueError as exc:
                raise PatchValidationError(f"Patch path escapes project root: {block.file_path}") from exc

            content = target_path.read_text(encoding="utf-8")
            if content.count(block.search) != 1:
                raise PatchValidationError(
                    f"SEARCH content must match exactly once in {block.file_path} before apply."
                )

            updated = content.replace(block.search, block.replace, 1)
            target_path.write_text(updated, encoding="utf-8")
