"""Parse SafeCode SEARCH/REPLACE patch text."""

from pathlib import Path
from uuid import uuid4

from safecode.patch.models import PatchBlock, PatchProposal
from safecode.utils.time import utc_now_iso


class PatchParseError(ValueError):
    """Raised when patch text does not match the SafeCode patch format."""


def _strip_to_envelope(text: str) -> str:
    """Extract from *** Begin Patch to *** End Patch, discarding surrounding prose."""
    start = text.find("*** Begin Patch")
    end_marker = "*** End Patch"
    end = text.find(end_marker, start if start >= 0 else 0)
    if start >= 0 and end >= 0:
        return text[start : end + len(end_marker)].strip()
    return text.strip()


class PatchParser:
    """Convert raw patch text into PatchProposal models."""

    def parse(self, patch_text: str, task: str) -> PatchProposal:
        """Parse patch text supporting multiple Update File blocks and leading prose."""
        clean = _strip_to_envelope(patch_text)
        lines = clean.splitlines()
        self._validate_envelope(lines)
        blocks = self._parse_all_blocks(lines)
        return PatchProposal(
            id=f"patch_{uuid4().hex[:8]}",
            task=task,
            blocks=blocks,
            created_at=utc_now_iso(),
            model="mock",
        )

    def _validate_envelope(self, lines: list[str]) -> None:
        if len(lines) < 5:
            raise PatchParseError("Patch is too short.")
        if lines[0] != "*** Begin Patch":
            raise PatchParseError("Patch must start with '*** Begin Patch'.")
        if lines[-1] != "*** End Patch":
            raise PatchParseError("Patch must end with '*** End Patch'.")

    def _is_operation_line(self, line: str) -> bool:
        return (
            line.startswith("*** Update File:")
            or line.startswith("*** Add File:")
            or line.startswith("*** Delete File:")
        )

    def _parse_all_blocks(self, lines: list[str]) -> list[PatchBlock]:
        """Split on operation markers and parse each file block."""
        # lines[0] = "*** Begin Patch", lines[-1] = "*** End Patch"
        inner = lines[1:-1]
        op_indices = [i for i, line in enumerate(inner) if self._is_operation_line(line)]
        if not op_indices:
            raise PatchParseError("Patch must contain at least one file operation.")
        blocks = []
        for idx, op_idx in enumerate(op_indices):
            end_idx = op_indices[idx + 1] if idx + 1 < len(op_indices) else len(inner)
            block_lines = inner[op_idx:end_idx]
            result = self._parse_single_block(block_lines)
            if result is not None:
                blocks.append(result)
        if not blocks:
            raise PatchParseError("Patch contained no actionable file operations.")
        return blocks

    def _parse_single_block(self, block_lines: list[str]) -> "PatchBlock | None":
        """Parse one file operation block (from its operation line to the next)."""
        op_line = block_lines[0]
        if not op_line.startswith("*** Update File:"):
            raise PatchParseError(
                f"Unsupported operation '{op_line}'; supports Update File only."
            )
        file_path = self._parse_update_file(op_line)

        search_index = next(
            (i for i, line in enumerate(block_lines) if line == "SEARCH:"), None
        )
        replace_index = next(
            (i for i, line in enumerate(block_lines) if line == "REPLACE:"), None
        )
        if search_index is None:
            raise PatchParseError(f"SEARCH marker must appear in block for {file_path}.")
        if replace_index is None:
            raise PatchParseError(f"REPLACE marker must appear in block for {file_path}.")
        if replace_index <= search_index:
            raise PatchParseError("REPLACE marker must appear after SEARCH.")

        search = "\n".join(block_lines[search_index + 1 : replace_index]).strip("\n")
        replace = "\n".join(block_lines[replace_index + 1 :]).strip("\n")

        if not search.strip():
            if not replace.strip():
                # Both empty: model is touching/creating an empty file. Skip silently.
                return None
            raise PatchParseError(f"SEARCH content cannot be empty in block for {file_path}.")

        return PatchBlock(
            operation="update",
            file_path=file_path,
            search=search,
            replace=replace,
        )

    def _parse_update_file(self, line: str) -> Path:
        raw_path = line.removeprefix("*** Update File:").strip()
        if not raw_path:
            raise PatchParseError("Update File path cannot be empty.")
        return Path(raw_path)
