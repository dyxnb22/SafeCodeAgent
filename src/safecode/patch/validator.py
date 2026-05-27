"""Validate patch proposals before preview or apply."""

from pathlib import Path

from safecode.patch.models import PatchBlock, PatchProposal


class PatchValidationError(ValueError):
    """Raised when a parsed patch is unsafe or cannot be applied."""


class PatchValidator:
    """Ensure patches are safe and deterministic."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def validate(self, proposal: PatchProposal) -> None:
        """Raise if the patch cannot be safely applied."""
        if not proposal.blocks:
            raise PatchValidationError("Patch proposal must contain at least one block.")

        for block in proposal.blocks:
            self._validate_block(block)

    def _validate_block(self, block: PatchBlock) -> None:
        """Validate one v0.1.2 update block."""
        if block.operation != "update":
            raise PatchValidationError("v0.1.2 supports update blocks only.")
        if block.search is None or not block.search.strip():
            raise PatchValidationError("Update block SEARCH cannot be empty.")
        if block.replace is None:
            raise PatchValidationError("Update block REPLACE cannot be missing.")

        target_path = self._resolve_target(block.file_path)
        if not target_path.exists():
            raise PatchValidationError(f"Target file does not exist: {block.file_path}")
        if not target_path.is_file():
            raise PatchValidationError(f"Target path is not a file: {block.file_path}")

        content = target_path.read_text(encoding="utf-8")
        count = content.count(block.search)
        if count == 0:
            raise PatchValidationError(f"SEARCH content was not found in {block.file_path}.")
        if count > 1:
            raise PatchValidationError(f"SEARCH content matched {count} times in {block.file_path}.")

    def _resolve_target(self, file_path: Path) -> Path:
        """Resolve a patch path and ensure it stays inside project_root."""
        target_path = (self.project_root / file_path).resolve()
        try:
            target_path.relative_to(self.project_root)
        except ValueError as exc:
            raise PatchValidationError(f"Patch path escapes project root: {file_path}") from exc
        return target_path
