"""Select relevant files for a task."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from safecode.index.files import FileIndexer
from safecode.memory.facade import MemoryFacade

_RECENCY_BONUS = 2
_GIT_LOG_N = 50


@dataclass(frozen=True)
class SelectedContextSource:
    """One selected context source with ranking metadata."""

    path: str
    score: int
    reason: str


@dataclass
class _RecencyCache:
    """HEAD-invalidated cache for recently git-touched file names."""

    head: str = ""
    recent_files: frozenset[str] = field(default_factory=frozenset)


def _get_head(project_root: Path) -> str:
    """Return current HEAD commit hash, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(project_root), shell=False, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def _get_recent_files(project_root: Path, n: int = _GIT_LOG_N) -> frozenset[str]:
    """Return basenames of files touched in the last n commits via git log."""
    try:
        result = subprocess.run(
            ["git", "log", f"-n{n}", "--name-only", "--pretty=format:"],
            capture_output=True, text=True, cwd=str(project_root), shell=False, timeout=10,
        )
        if result.returncode != 0:
            return frozenset()
        names: set[str] = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                names.add(line)
                names.add(Path(line).name)
        return frozenset(names)
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()


class ContextSelector:
    """Keyword-based context selector with git-recency boost."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._recency_cache = _RecencyCache()
        self.last_warnings: dict[str, list[str]] = {}

    def _recent_files(self) -> frozenset[str]:
        """Return recently git-touched file names, cached by HEAD."""
        head = _get_head(self.project_root)
        if head and head == self._recency_cache.head:
            return self._recency_cache.recent_files
        recent = _get_recent_files(self.project_root)
        self._recency_cache = _RecencyCache(head=head, recent_files=recent)
        return recent

    def select(self, query: str, limit: int = 10) -> list[str]:
        """Return files with path tokens that match query tokens."""
        return [source.path for source in self.select_sources(query, limit)]

    def select_sources(self, query: str, limit: int = 10) -> list[SelectedContextSource]:
        """Return ranked file sources; recently git-touched files get a score bonus."""
        self.last_warnings = {}
        if limit <= 0:
            return []
        tokens = {part.lower() for part in query.replace("/", " ").replace("_", " ").split() if part}
        indexed = FileIndexer(self.project_root).index()
        indexed_paths = {item.path for item in indexed}
        recent = self._recent_files()
        scored: list[SelectedContextSource] = []
        if tokens:
            for item in indexed:
                path_text = item.path.lower()
                matched = sorted(token for token in tokens if token in path_text)
                if not matched:
                    continue
                base_score = len(matched)
                file_name = Path(item.path).name
                is_recent = item.path in recent or file_name in recent
                bonus = _RECENCY_BONUS if is_recent else 0
                reason = f"path matched: {', '.join(matched)}"
                if is_recent:
                    reason += "; recently modified"
                scored.append(
                    SelectedContextSource(
                        path=item.path,
                        score=base_score + bonus,
                        reason=reason,
                    )
                )
        ranked = sorted(scored, key=lambda source: (-source.score, source.path))
        pinned = self._pinned_sources(indexed_paths, limit)
        pinned_paths = {source.path for source in pinned}
        keyword_quota = max(limit - len(pinned), 0)
        selected = [source for source in ranked if source.path not in pinned_paths][:keyword_quota]
        selected.extend(pinned)
        return selected[:limit]

    def _pinned_sources(self, indexed_paths: set[str], limit: int) -> list[SelectedContextSource]:
        """Return pinned sources that still pass safe indexing."""
        facade = MemoryFacade(self.project_root)
        quota = max(1, limit // 4)
        missing: list[str] = []
        invalid: list[str] = []
        sources: list[SelectedContextSource] = []

        for raw_pin in facade.read_pinned_files():
            try:
                pin = facade.normalize_project_path(raw_pin)
            except ValueError:
                invalid.append(raw_pin)
                continue
            if pin not in indexed_paths:
                if not (self.project_root / pin).exists():
                    missing.append(pin)
                continue
            if self._looks_binary(self.project_root / pin):
                continue
            sources.append(SelectedContextSource(path=pin, score=1, reason="pinned file"))

        if missing:
            self.last_warnings["pinned_missing"] = sorted(missing)
        if invalid:
            self.last_warnings["pinned_invalid"] = sorted(invalid)
        return sorted(sources, key=lambda source: source.path)[:quota]

    def _looks_binary(self, path: Path) -> bool:
        try:
            with path.open("rb") as file:
                return b"\0" in file.read(1024)
        except OSError:
            return True
