"""Select relevant files for a task."""

from pathlib import Path

from safecode.index.files import FileIndexer


class ContextSelector:
    """Keyword-based context selector."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def select(self, query: str, limit: int = 10) -> list[str]:
        """Return files with path tokens that match query tokens."""
        tokens = {part.lower() for part in query.replace("/", " ").replace("_", " ").split() if part}
        indexed = FileIndexer(self.project_root).index()
        scored: list[tuple[int, str]] = []
        for item in indexed:
            path_text = item.path.lower()
            score = sum(1 for token in tokens if token in path_text)
            if score:
                scored.append((score, item.path))
        return [path for _, path in sorted(scored, reverse=True)[:limit]]
