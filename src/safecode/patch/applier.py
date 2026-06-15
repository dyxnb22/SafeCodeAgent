"""Apply validated patch proposals to files transactionally."""

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from safecode.patch.models import PatchProposal
from safecode.patch.validator import PatchValidationError
from safecode.sandbox.filesystem import FilesystemBoundary


class PatchApplyError(PatchValidationError):
    """Structured error from a failed filesystem mutation (B7).

    Extends PatchValidationError so existing callers that catch
    PatchValidationError continue to work.
    """

    def __init__(self, failure_reason: str, path: str = "") -> None:
        super().__init__(f"Apply failed and was rolled back: {failure_reason} (path={path!r})")
        self.failure_reason = failure_reason
        self.path = path


@dataclass(frozen=True)
class PreparedOperation:
    """One validated file replacement."""

    relative_path: Path
    target_path: Path
    original_content: str
    updated_content: str
    file_mode: int
    file_device: int | None
    file_inode: int | None
    operation: str = "update"  # "update", "create", "delete"


class PatchApplier:
    """Write patch changes after user approval and checkpoint creation."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.filesystem = FilesystemBoundary(self.project_root)

    def apply(self, proposal: PatchProposal) -> None:
        """Apply a validated patch proposal with rollback on failure.

        Supports update (B6: also create and delete) operation types.
        Wraps filesystem mutations to surface PermissionError/OSError as
        PatchApplyError rather than letting them bubble uncaught (B7).
        """
        operations = self._prepare_operations(proposal)
        applied: list[tuple[Path, PreparedOperation]] = []

        try:
            for op in operations:
                if op.operation == "delete":
                    # B6: delete — remove the file; checkpoint already backed it up.
                    try:
                        if op.target_path.exists():
                            op.target_path.unlink()
                    except (PermissionError, OSError) as exc:
                        raise PatchApplyError(
                            failure_reason=f"delete failed: {type(exc).__name__}: {exc}",
                            path=str(op.relative_path),
                        ) from exc
                    applied.append((op.target_path, op))
                elif op.operation == "create":
                    # B6: create — write new file (no prior content check).
                    try:
                        self._atomic_write(op.target_path, op.updated_content, op.file_mode)
                    except (PermissionError, OSError) as exc:
                        raise PatchApplyError(
                            failure_reason=f"create failed: {type(exc).__name__}: {exc}",
                            path=str(op.relative_path),
                        ) from exc
                    applied.append((op.target_path, op))
                else:
                    # update — existing behaviour with B7 error wrapping.
                    resolved_path = self._validate_write_target(op)
                    try:
                        current_content = resolved_path.read_text(encoding="utf-8")
                    except (PermissionError, OSError) as exc:
                        raise PatchApplyError(
                            failure_reason=f"read before update failed: {type(exc).__name__}: {exc}",
                            path=str(op.relative_path),
                        ) from exc
                    if current_content != op.original_content:
                        raise PatchValidationError(f"File changed after validation: {op.target_path}")
                    try:
                        self._atomic_write(resolved_path, op.updated_content, op.file_mode)
                    except (PermissionError, OSError) as exc:
                        raise PatchApplyError(
                            failure_reason=f"write failed: {type(exc).__name__}: {exc}",
                            path=str(op.relative_path),
                        ) from exc
                    applied.append((resolved_path, op))

        except (PatchApplyError, PatchValidationError, Exception) as exc:
            rollback_errors: list[str] = []
            for resolved_path, op in reversed(applied):
                try:
                    if op.operation == "delete":
                        # Restore deleted file from original_content
                        self._atomic_write(resolved_path, op.original_content, op.file_mode)
                    elif op.operation == "create":
                        # Remove the newly created file
                        if resolved_path.exists():
                            resolved_path.unlink()
                    else:
                        self._atomic_write(resolved_path, op.original_content, op.file_mode)
                except Exception as rollback_exc:
                    rollback_errors.append(f"{op.target_path}: {rollback_exc}")
            if rollback_errors:
                raise PatchValidationError(
                    f"Transactional apply failed and rollback also failed: {exc}; rollback_errors={rollback_errors}"
                ) from exc
            if isinstance(exc, (PatchApplyError, PatchValidationError)):
                raise
            raise PatchValidationError(f"Transactional apply failed and was rolled back: {exc}") from exc

    def _prepare_operations(self, proposal: PatchProposal) -> list[PreparedOperation]:
        """Validate and render all file operations before writing any file.

        B6: Supports 'update', 'create', and 'delete' operations.
        """
        operations: list[PreparedOperation] = []
        for block in proposal.blocks:
            op_type = block.operation

            if op_type not in ("update", "create", "delete"):
                raise PatchValidationError(f"Unknown operation type: {op_type!r}. Supported: update, create, delete.")

            try:
                original_path = self.project_root / block.file_path
                if original_path.is_symlink():
                    raise PatchValidationError(f"Refusing to apply to symlinked path: {block.file_path}")
                # For create, validate parent dir not outside root; file need not exist yet.
                if op_type == "create":
                    target_path = original_path.resolve()
                    # Verify it stays inside project root.
                    target_path.relative_to(self.project_root)
                else:
                    target_path = self.filesystem.validate(original_path)
            except (PermissionError, ValueError) as exc:
                raise PatchValidationError(str(exc)) from exc

            if op_type == "update":
                if block.search is None or block.replace is None:
                    raise PatchValidationError("Update block requires SEARCH and REPLACE.")
                try:
                    content = target_path.read_text(encoding="utf-8")
                except UnicodeDecodeError as exc:
                    raise PatchValidationError(f"Cannot apply text patch to non-UTF-8 file: {block.file_path}") from exc
                if content.count(block.search) != 1:
                    raise PatchValidationError(
                        f"SEARCH content must match exactly once in {block.file_path} before apply."
                    )
                updated = content.replace(block.search, block.replace, 1)
                stat_info = target_path.stat()
                operations.append(PreparedOperation(
                    relative_path=block.file_path,
                    target_path=target_path,
                    original_content=content,
                    updated_content=updated,
                    file_mode=stat.S_IMODE(stat_info.st_mode),
                    file_device=stat_info.st_dev if hasattr(stat_info, "st_dev") else None,
                    file_inode=stat_info.st_ino if hasattr(stat_info, "st_ino") else None,
                    operation="update",
                ))

            elif op_type == "create":
                # B6: create — content is the new file body; file must not exist yet
                # (or caller explicitly wants to overwrite — treat as create either way).
                new_content = block.content or ""
                target_path.parent.mkdir(parents=True, exist_ok=True)
                operations.append(PreparedOperation(
                    relative_path=block.file_path,
                    target_path=target_path,
                    original_content="",
                    updated_content=new_content,
                    file_mode=0o644,
                    file_device=None,
                    file_inode=None,
                    operation="create",
                ))

            else:  # delete
                # B6: delete — remove file; checkpoint (created before apply) holds the backup.
                try:
                    content = target_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    content = ""
                stat_info = target_path.stat() if target_path.exists() else None
                operations.append(PreparedOperation(
                    relative_path=block.file_path,
                    target_path=target_path,
                    original_content=content,
                    updated_content="",
                    file_mode=stat.S_IMODE(stat_info.st_mode) if stat_info else 0o644,
                    file_device=stat_info.st_dev if stat_info and hasattr(stat_info, "st_dev") else None,
                    file_inode=stat_info.st_ino if stat_info and hasattr(stat_info, "st_ino") else None,
                    operation="delete",
                ))

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

    def _validate_write_target(self, operation: PreparedOperation) -> Path:
        """Re-validate the target before applying changes."""
        original_path = self.project_root / operation.relative_path
        if original_path.is_symlink():
            raise PatchValidationError(f"Refusing to apply to symlinked path: {operation.relative_path}")
        try:
            resolved = self.filesystem.validate(original_path)
        except PermissionError as exc:
            raise PatchValidationError(str(exc)) from exc
        if resolved != operation.target_path:
            raise PatchValidationError(f"Resolved path changed after validation: {operation.relative_path}")
        try:
            stat_info = resolved.stat()
        except FileNotFoundError as exc:
            raise PatchValidationError(f"File missing after validation: {operation.relative_path}") from exc
        if operation.file_inode is not None and stat_info.st_ino != operation.file_inode:
            raise PatchValidationError(f"File identity changed after validation: {operation.relative_path}")
        if operation.file_device is not None and stat_info.st_dev != operation.file_device:
            raise PatchValidationError(f"File identity changed after validation: {operation.relative_path}")
        return resolved
