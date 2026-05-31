"""Select relevant files for a task."""

from dataclasses import dataclass
from pathlib import Path

from safecode.index.files import FileIndexer


@dataclass(frozen=True)
class SelectedContextSource:
    """One selected context source with ranking metadata."""

    path: str
    score: int
    reason: str


class ContextSelector:
    """Keyword-based context selector."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def select(self, query: str, limit: int = 10) -> list[str]:
        """Return files with path tokens that match query tokens."""
        return [source.path for source in self.select_sources(query, limit)]

    def select_sources(self, query: str, limit: int = 10) -> list[SelectedContextSource]:
        """Return ranked file sources with simple path-match reasons."""
        tokens = {part.lower() for part in query.replace("/", " ").replace("_", " ").split() if part}
        indexed = FileIndexer(self.project_root).index()
        scored: list[SelectedContextSource] = []
        for item in indexed:
            path_text = item.path.lower()
            matched = sorted(token for token in tokens if token in path_text)
            if matched:
                scored.append(
                    SelectedContextSource(
                        path=item.path,
                        score=len(matched),
                        reason=f"path matched: {', '.join(matched)}",
                    )
                )
        return sorted(scored, key=lambda source: (-source.score, source.path))[:limit]
