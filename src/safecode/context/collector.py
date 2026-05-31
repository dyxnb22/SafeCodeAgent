"""Collect safe, bounded project context for the agent."""

from fnmatch import fnmatch
from dataclasses import asdict
import os
from pathlib import Path

from safecode.config import SafeCodeConfig
from safecode.context.budget import ContextBudget, ContextBudgetPacker
from safecode.context.redactor import redact_secrets
from safecode.sandbox.filesystem import FilesystemBoundary


SKIP_DIRS = {".git", ".sac", ".venv", "__pycache__", ".pytest_cache"}
SKIP_FILES = {".DS_Store"}
SENSITIVE_NAMES = {".env", "id_rsa", "id_dsa", "credentials", "token"}
SENSITIVE_PATTERNS = {
    ".env*",
    "*.pem",
    "*.key",
    "*.p12",
    "id_*",
    "*credential*",
    "*token*",
    "*secret*",
    "*password*",
}


class ContextCollector:
    """Read project metadata while avoiding sensitive files."""

    def __init__(self, project_root: Path, config: SafeCodeConfig | None = None) -> None:
        self.project_root = project_root.resolve()
        self.config = config or SafeCodeConfig.load(project_root)
        self.filesystem = FilesystemBoundary(self.project_root, self.config)

    def collect(self, query: str | None = None) -> dict:
        """Return bounded project context with optional task-focused sources."""
        files = self._list_files()
        context = {
            "project_root": "[PROJECT_ROOT]",
            "files": files,
            "readme": self._read_limited("README.md", self.config.max_file_lines),
            "pyproject": self._read_limited("pyproject.toml", self.config.max_file_lines),
            "repo_map": self._repo_map_summary(),
        }
        if query:
            context["selected_context"] = self._selected_context(query)
        return self._cap_context(context)

    def _list_files(self) -> list[str]:
        """Return a bounded, sorted file list relative to project_root."""
        files: list[str] = []

        for root, dir_names, file_names in os.walk(self.project_root, followlinks=False):
            root_path = Path(root)
            dir_names[:] = sorted(
                dir_name
                for dir_name in dir_names
                if not self._should_skip(root_path.joinpath(dir_name).relative_to(self.project_root))
                and not root_path.joinpath(dir_name).is_symlink()
            )

            for file_name in sorted(file_names):
                path = root_path / file_name
                relative = path.relative_to(self.project_root)

                if len(files) >= self.config.max_tree_files:
                    break

                if self._should_skip(relative):
                    continue

                if path.is_symlink():
                    continue

                if path.is_file():
                    files.append(relative.as_posix())

            if len(files) >= self.config.max_tree_files:
                break

        return files

    def _read_limited(self, relative_path: str, max_lines: int) -> str | None:
        """Read at most max_lines from a UTF-8 text file."""
        relative = Path(relative_path)
        if self._should_skip(relative):
            return None

        path = self.project_root / relative
        if path.is_symlink() or not path.exists() or not path.is_file():
            return None
        try:
            self.filesystem.validate(path)
        except PermissionError:
            return None
        if path.stat().st_size > self.config.max_file_bytes:
            return None

        lines: list[str] = []
        with path.open("r", encoding="utf-8", errors="replace") as file:
            for index, line in enumerate(file):
                if index >= max_lines:
                    break
                lines.append(line)
        return redact_secrets("".join(lines))

    def _should_skip(self, relative_path: Path) -> bool:
        """Skip generated, internal, and sensitive paths."""
        lowered_parts = {part.lower() for part in relative_path.parts}
        name = relative_path.name.lower()
        configured_sensitive = {item.lower() for item in self.config.sandbox.sensitive_names}

        if lowered_parts & SKIP_DIRS:
            return True
        if name in SKIP_FILES:
            return True
        if name in SENSITIVE_NAMES:
            return True
        if name in configured_sensitive or lowered_parts & configured_sensitive:
            return True
        relative_text = relative_path.as_posix().lower()
        if any(fnmatch(name, pattern) or fnmatch(relative_text, pattern) for pattern in SENSITIVE_PATTERNS):
            return True
        return False

    def _cap_context(self, context: dict) -> dict:
        """Keep context under a global byte budget and report packing metadata."""
        capped, report = ContextBudgetPacker(ContextBudget.from_max_chars(self.config.max_context_chars)).pack(context)
        capped["context_budget"] = report.to_dict()
        return capped

    def _repo_map_summary(self) -> dict:
        """Return a compact repository intelligence summary for planning."""
        from safecode.index.repo_map import RepoMapBuilder

        repo_map = RepoMapBuilder(self.project_root).build()
        return {
            "counts": {
                "files": len(repo_map.files),
                "symbols": len(repo_map.symbols),
                "imports": len(repo_map.imports),
                "tests": len(repo_map.tests),
                "commands": len(repo_map.commands),
                "entrypoints": len(repo_map.entrypoints),
            },
            "symbols": [asdict(item) for item in repo_map.symbols[:50]],
            "tests": [asdict(item) for item in repo_map.tests[:50]],
            "commands": [asdict(item) for item in repo_map.commands[:20]],
            "entrypoints": [asdict(item) for item in repo_map.entrypoints[:20]],
        }

    def _selected_context(self, query: str) -> dict:
        """Select and include small snippets for files related to the query."""
        from safecode.context.selector import ContextSelector

        sources = ContextSelector(self.project_root).select_sources(query, limit=5)
        snippets = {
            source.path: self._read_limited(source.path, max_lines=min(self.config.max_file_lines, 80))
            for source in sources
        }
        return {
            "sources": [asdict(source) for source in sources],
            "snippets": {path: text for path, text in snippets.items() if text is not None},
        }
