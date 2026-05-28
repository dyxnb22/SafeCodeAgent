"""Apply validated patch proposals to files transactionally."""

import tempfile
from pathlib import Path

from safecode.patch.models import PatchProposal
from safecode.patch.validator import PatchValidationError
from safecode.sandbox.filesystem import FilesystemBoundary


class PatchApplier:
    """Write patch changes after user approval and checkpoint creation."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.filesystem = FilesystemBoundary(self.project_root)

    def apply(self, proposal: PatchProposal) -> None:
        """Apply a validated patch proposal with rollback on failure."""
        operations = self._prepare_operations(proposal)
        originals = {target: target.read_text(encoding="utf-8") for target, _ in operations}
        replaced: list[Path] = []

        try:
            for target_path, updated in operations:
                self._atomic_write(target_path, updated)
                replaced.append(target_path)
        except Exception as exc:
            for target_path in reversed(replaced):
                self._atomic_write(target_path, originals[target_path])
            raise PatchValidationError(f"Transactional apply failed and was rolled back: {exc}") from exc

    def _prepare_operations(self, proposal: PatchProposal) -> list[tuple[Path, str]]:
        """Validate and render all file updates before writing any file."""
        operations: list[tuple[Path, str]] = []
        for block in proposal.blocks:
            if block.operation != "update":
                raise PatchValidationError("v0.1.3 can apply update blocks only.")
            if block.search is None or block.replace is None:
                raise PatchValidationError("Update block requires SEARCH and REPLACE.")

            try:
                target_path = self.filesystem.validate(self.project_root / block.file_path)
            except PermissionError as exc:
                raise PatchValidationError(str(exc)) from exc

            content = target_path.read_text(encoding="utf-8")
            if content.count(block.search) != 1:
                raise PatchValidationError(
                    f"SEARCH content must match exactly once in {block.file_path} before apply."
                )

            updated = content.replace(block.search, block.replace, 1)
            operations.append((target_path, updated))
        return operations

    def _atomic_write(self, target_path: Path, content: str) -> None:
        """Write content through a temp file and atomic replace."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target_path.parent, delete=False) as file:
            temp_path = Path(file.name)
            file.write(content)
        try:
            temp_path.replace(target_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
