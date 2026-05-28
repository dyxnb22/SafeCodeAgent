"""Apply validated patch proposals to files transactionally."""

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from safecode.patch.models import PatchProposal
from safecode.patch.validator import PatchValidationError
from safecode.sandbox.filesystem import FilesystemBoundary


@dataclass(frozen=True)
class PreparedOperation:
    """One validated file replacement."""

    target_path: Path
    original_content: str
    updated_content: str
    file_mode: int


class PatchApplier:
    """Write patch changes after user approval and checkpoint creation."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.filesystem = FilesystemBoundary(self.project_root)

    def apply(self, proposal: PatchProposal) -> None:
        """Apply a validated patch proposal with rollback on failure."""
        operations = self._prepare_operations(proposal)
        replaced: list[PreparedOperation] = []

        try:
            for operation in operations:
                current_content = operation.target_path.read_text(encoding="utf-8")
                if current_content != operation.original_content:
                    raise PatchValidationError(f"File changed after validation: {operation.target_path}")
                self._atomic_write(operation.target_path, operation.updated_content, operation.file_mode)
                replaced.append(operation)
        except Exception as exc:
            rollback_errors: list[str] = []
            for operation in reversed(replaced):
                try:
                    self._atomic_write(operation.target_path, operation.original_content, operation.file_mode)
                except Exception as rollback_exc:
                    rollback_errors.append(f"{operation.target_path}: {rollback_exc}")
            if rollback_errors:
                raise PatchValidationError(
                    f"Transactional apply failed and rollback also failed: {exc}; rollback_errors={rollback_errors}"
                ) from exc
            raise PatchValidationError(f"Transactional apply failed and was rolled back: {exc}") from exc

    def _prepare_operations(self, proposal: PatchProposal) -> list[PreparedOperation]:
        """Validate and render all file updates before writing any file."""
        operations: list[PreparedOperation] = []
        for block in proposal.blocks:
            if block.operation != "update":
                raise PatchValidationError("v0.1.3 can apply update blocks only.")
            if block.search is None or block.replace is None:
                raise PatchValidationError("Update block requires SEARCH and REPLACE.")

            try:
                target_path = self.filesystem.validate(self.project_root / block.file_path)
            except PermissionError as exc:
                raise PatchValidationError(str(exc)) from exc

            try:
                content = target_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise PatchValidationError(f"Cannot apply text patch to non-UTF-8 file: {block.file_path}") from exc
            if content.count(block.search) != 1:
                raise PatchValidationError(
                    f"SEARCH content must match exactly once in {block.file_path} before apply."
                )

            updated = content.replace(block.search, block.replace, 1)
            operations.append(
                PreparedOperation(
                    target_path=target_path,
                    original_content=content,
                    updated_content=updated,
                    file_mode=stat.S_IMODE(target_path.stat().st_mode),
                )
            )
        return operations

    def _atomic_write(self, target_path: Path, content: str, file_mode: int | None = None) -> None:
        """Write content through a temp file and atomic replace."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target_path.parent, delete=False) as file:
            temp_path = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        if file_mode is not None:
            temp_path.chmod(file_mode)
        try:
            temp_path.replace(target_path)
            self._fsync_directory(target_path.parent)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _fsync_directory(self, directory: Path) -> None:
        """Best-effort directory fsync after atomic replace."""
        if not hasattr(os, "O_DIRECTORY"):
            return
        try:
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
