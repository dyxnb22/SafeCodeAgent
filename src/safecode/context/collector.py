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

    def collect(
        self,
        query: str | None = None,
        *,
        seed_files: list[str] | None = None,
        include_git_context: bool = False,
        include_diagnostics: bool = False,
        conversation_files: list[str] | None = None,
    ) -> dict:
        """Return bounded project context with optional task-focused sources.

        v5.3.0 additions:
        - seed_files: list of paths to seed import-graph context (first-degree imports
          pre-loaded up to N=5 per seed file, budget-gated).
        - include_git_context: when True, inject recent git activity block.
        """
        files, file_tree_truncated = self._list_files()
        context: dict = {
            "project_root": "[PROJECT_ROOT]",
            "files": files,
            "readme": self._read_limited("README.md", self.config.max_file_lines),
            "pyproject": self._read_limited("pyproject.toml", self.config.max_file_lines),
            "repo_map": self._repo_map_summary(),
        }
        # B5: expose truncation flag so the model and display layers can see it.
        if file_tree_truncated:
            context["file_tree_meta"] = {"truncated": True, "cap": self.config.max_tree_files}
        if query:
            context["selected_context"] = self._selected_context(query, conversation_files=conversation_files)
        if seed_files:
            context["import_context"] = self._import_graph_context(seed_files)
        if include_git_context:
            git_block = self._git_context_block()
            if git_block:
                context["git_context"] = git_block
        if include_diagnostics:
            diag_block = self._diagnostics_context_block()
            if diag_block:
                context["diagnostics"] = diag_block
        # v6.30: inject cross-session workspace memory so the agent builds on
        # lessons learned in previous sessions (test commands, bug fixes, conventions).
        workspace_mem_block = self._workspace_memory_block(query)
        if workspace_mem_block:
            context["workspace_memory"] = workspace_mem_block
        return self._cap_context(context)

    def _import_graph_context(self, seed_files: list[str]) -> dict:
        """Return import-graph-seeded snippets for seed_files (v5.3.0)."""
        try:
            from safecode.index.import_graph import ImportGraph
            graph = ImportGraph(self.project_root)
            seeded: dict[str, list[str]] = {}
            all_imports: set[str] = set()
            for seed in seed_files:
                imports = graph.first_degree_imports(seed, limit=5)
                if imports:
                    seeded[seed] = imports
                    all_imports.update(imports)

            # Read snippets for all discovered imports (budget-gated via _cap_context)
            snippets: dict[str, str | None] = {}
            for rel_path in sorted(all_imports)[:10]:  # hard cap at 10 total
                if not self._should_skip(Path(rel_path)):
                    snippets[rel_path] = self._read_limited(rel_path, max_lines=40)

            return {
                "seeds": list(seed_files),
                "first_degree_imports": seeded,
                "snippets": {p: s for p, s in snippets.items() if s is not None},
            }
        except Exception:
            return {}

    def _git_context_block(self) -> str:
        """Return a bounded git context block for this project (v5.3.0)."""
        try:
            from safecode.context.git_context import collect_git_context
            ctx = collect_git_context(self.project_root)
            return ctx.to_context_block()
        except Exception:
            return ""

    def _diagnostics_context_block(self) -> dict:
        """Return bounded local diagnostics for model context."""
        try:
            from safecode.context.diagnostics import diagnostics_context_block

            return diagnostics_context_block(self.project_root, self.config)
        except Exception:
            return {}

    def _workspace_memory_block(self, query: str | None) -> str:
        """Return a bounded cross-session workspace memory block (v6.30).

        Loads the most recent entries from ``.sac/workspace_memory.jsonl``
        ranked by relevance to *query* and recency. Fails closed — returns
        empty string on any error.
        """
        try:
            from safecode.memory.workspace_memory import WorkspaceMemoryStore

            store = WorkspaceMemoryStore(self.project_root)
            return store.top_context_block(query=query)
        except Exception:
            return ""

    def _list_files(self) -> tuple[list[str], bool]:
        """Return (file_list, truncated) relative to project_root.

        Returns truncated=True when the max_tree_files cap was hit (B5).
        """
        files: list[str] = []
        truncated = False

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
                    truncated = True
                    break

                if self._should_skip(relative):
                    continue

                if path.is_symlink():
                    continue

                if path.is_file():
                    files.append(relative.as_posix())

            if len(files) >= self.config.max_tree_files and not truncated:
                # Check whether there are more files to walk (could be more dirs).
                truncated = True
                break
            if truncated:
                break

        return files, truncated

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
        if self._looks_binary(path):
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

    def _selected_context(self, query: str, *, conversation_files: list[str] | None = None) -> dict:
        """Select and include small snippets for files related to the query."""
        from safecode.context.selector import ContextSelector

        selector = ContextSelector(self.project_root)
        sources = selector.select_sources(query, limit=5, conversation_files=conversation_files)
        snippets = {
            source.path: self._read_limited(source.path, max_lines=min(self.config.max_file_lines, 80))
            for source in sources
        }
        result: dict = {
            "sources": [asdict(source) for source in sources],
            "snippets": {path: text for path, text in snippets.items() if text is not None},
            "warnings": selector.last_warnings,
        }
        # v6.8.1: per-file git log + diff (opt-in via config_git_per_file)
        if getattr(self.config, "context_git_per_file", False):
            try:
                from safecode.context.git_context import collect_per_file_git_context
                git_block = collect_per_file_git_context(
                    self.project_root, [s.path for s in sources]
                )
                if git_block:
                    result["per_file_git_context"] = git_block
            except Exception:
                pass
        return result

    def _looks_binary(self, path: Path) -> bool:
        """Detect obvious binary files without reading them into text context."""
        try:
            with path.open("rb") as file:
                return b"\0" in file.read(1024)
        except OSError:
            return True
