"""Parse SafeCode SEARCH/REPLACE patch text."""

from pathlib import Path
from uuid import uuid4

from safecode.patch.models import PatchBlock, PatchProposal
from safecode.utils.time import utc_now_iso


class PatchParseError(ValueError):
    """Raised when patch text does not match the SafeCode patch format."""


class PatchParser:
    """Convert raw patch text into PatchProposal models."""

    def parse(self, patch_text: str, task: str) -> PatchProposal:
        """Parse patch text.

        v0.1.1 intentionally supports one Update File block only.
        """
        lines = patch_text.strip().splitlines()
        self._validate_envelope(lines)

        update_index = self._find_single_update_line(lines)
        file_path = self._parse_update_file(lines[update_index])

        search_index = self._find_marker(lines, "SEARCH:")
        replace_index = self._find_marker(lines, "REPLACE:")

        if search_index <= update_index:
            raise PatchParseError("SEARCH marker must appear after Update File.")
        if replace_index <= search_index:
            raise PatchParseError("REPLACE marker must appear after SEARCH.")

        search = "\n".join(lines[search_index + 1 : replace_index]).strip("\n")
        replace = "\n".join(lines[replace_index + 1 : -1]).strip("\n")

        if not search.strip():
            raise PatchParseError("SEARCH content cannot be empty.")

        block = PatchBlock(
            operation="update",
            file_path=file_path,
            search=search,
            replace=replace,
        )
        return PatchProposal(
            id=f"patch_{uuid4().hex[:8]}",
            task=task,
            blocks=[block],
            created_at=utc_now_iso(),
            model="mock",
        )

    def _validate_envelope(self, lines: list[str]) -> None:
        """Ensure the patch has the required Begin/End markers."""
        if len(lines) < 5:
            raise PatchParseError("Patch is too short.")
        if lines[0] != "*** Begin Patch":
            raise PatchParseError("Patch must start with '*** Begin Patch'.")
        if lines[-1] != "*** End Patch":
            raise PatchParseError("Patch must end with '*** End Patch'.")

    def _find_single_update_line(self, lines: list[str]) -> int:
        """Find the one supported Update File operation."""
        operation_indexes = [
            index
            for index, line in enumerate(lines)
            if line.startswith("*** Update File:")
            or line.startswith("*** Add File:")
            or line.startswith("*** Delete File:")
        ]
        if not operation_indexes:
            raise PatchParseError("Patch must contain one Update File operation.")
        if len(operation_indexes) > 1:
            raise PatchParseError("v0.1.1 supports only one file operation per patch.")

        operation_line = lines[operation_indexes[0]]
        if not operation_line.startswith("*** Update File:"):
            raise PatchParseError("v0.1.1 supports Update File only.")

        return operation_indexes[0]

    def _parse_update_file(self, line: str) -> Path:
        """Extract the target file path from an Update File line."""
        raw_path = line.removeprefix("*** Update File:").strip()
        if not raw_path:
            raise PatchParseError("Update File path cannot be empty.")
        return Path(raw_path)

    def _find_marker(self, lines: list[str], marker: str) -> int:
        """Find a required marker line exactly once."""
        indexes = [index for index, line in enumerate(lines) if line == marker]
        if not indexes:
            raise PatchParseError(f"Patch must contain {marker}")
        if len(indexes) > 1:
            raise PatchParseError(f"Patch must contain {marker} only once.")
        return indexes[0]
