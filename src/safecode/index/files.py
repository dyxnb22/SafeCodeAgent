"""File index for project navigation."""

from dataclasses import dataclass
from pathlib import Path

from safecode.context.collector import ContextCollector


@dataclass(frozen=True)
class IndexedFile:
    """One indexed file."""

    path: str
    suffix: str


class FileIndexer:
    """Build a lightweight file index."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def index(self) -> list[IndexedFile]:
        """Index safe project files."""
        files = ContextCollector(self.project_root)._list_files()
        return [IndexedFile(path=file, suffix=Path(file).suffix) for file in files]
