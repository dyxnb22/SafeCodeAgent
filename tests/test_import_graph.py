"""Tests for v5.3.0 import graph context seeding."""

from __future__ import annotations

from pathlib import Path
import pytest


# ---------------------------------------------------------------------------
# Python import parsing
# ---------------------------------------------------------------------------

class TestParsePythonImports:
    def test_parse_absolute_imports(self):
        from safecode.index.import_graph import _parse_python_imports
        source = "import os\nimport sys\nimport safecode.config\n"
        result = _parse_python_imports(source)
        assert "os" in result
        assert "sys" in result
        assert "safecode.config" in result

    def test_parse_from_imports(self):
        from safecode.index.import_graph import _parse_python_imports
        source = "from pathlib import Path\nfrom safecode.config import SafeCodeConfig\n"
        result = _parse_python_imports(source)
        assert "pathlib" in result
        assert "safecode.config" in result

    def test_parse_relative_imports(self):
        from safecode.index.import_graph import _parse_python_imports
        source = "from .sibling import func\nfrom ..utils import helper\n"
        result = _parse_python_imports(source)
        assert ".sibling" in result
        assert "..utils" in result

    def test_invalid_syntax_returns_empty(self):
        from safecode.index.import_graph import _parse_python_imports
        result = _parse_python_imports("def broken(:\n    pass")
        assert result == []


# ---------------------------------------------------------------------------
# TypeScript import parsing
# ---------------------------------------------------------------------------

class TestParseTsImports:
    def test_parse_import_from(self):
        from safecode.index.import_graph import _parse_ts_imports
        source = "import { foo } from './utils';\nimport type { Bar } from '../types';\n"
        result = _parse_ts_imports(source)
        assert "./utils" in result
        assert "../types" in result

    def test_parse_require(self):
        from safecode.index.import_graph import _parse_ts_imports
        source = "const path = require('./helper');\n"
        result = _parse_ts_imports(source)
        assert "./helper" in result

    def test_skip_node_modules(self):
        from safecode.index.import_graph import _parse_ts_imports
        source = "import React from 'react';\n"
        result = _parse_ts_imports(source)
        assert "react" in result  # parser doesn't filter; resolution does


# ---------------------------------------------------------------------------
# Go import parsing
# ---------------------------------------------------------------------------

class TestParseGoImports:
    def test_parse_import_block(self):
        from safecode.index.import_graph import _parse_go_imports
        source = 'import (\n    "fmt"\n    "os"\n    "github.com/user/pkg"\n)\n'
        result = _parse_go_imports(source)
        assert "fmt" in result
        assert "os" in result
        assert "github.com/user/pkg" in result


# ---------------------------------------------------------------------------
# ImportGraph.first_degree_imports
# ---------------------------------------------------------------------------

class TestImportGraphFirstDegree:
    def test_python_first_degree_imports(self, tmp_path):
        from safecode.index.import_graph import ImportGraph

        # Create a mini Python project
        (tmp_path / "main.py").write_text("from utils import helper\nimport config\n")
        (tmp_path / "utils.py").write_text("def helper(): pass\n")
        (tmp_path / "config.py").write_text("DEBUG = True\n")

        graph = ImportGraph(tmp_path)
        imports = graph.first_degree_imports("main.py")
        # Should find utils.py and/or config.py
        assert len(imports) >= 1
        assert any("utils.py" in p or "config.py" in p for p in imports)

    def test_circular_imports_do_not_loop(self, tmp_path):
        from safecode.index.import_graph import ImportGraph

        # a.py imports b.py; b.py imports a.py
        (tmp_path / "a.py").write_text("from b import something\n")
        (tmp_path / "b.py").write_text("from a import other\n")

        graph = ImportGraph(tmp_path)
        imports_a = graph.first_degree_imports("a.py", limit=10)
        # Should return b.py without looping
        assert len(imports_a) <= 10
        assert "b.py" in imports_a or len(imports_a) == 0

    def test_limit_respected(self, tmp_path):
        from safecode.index.import_graph import ImportGraph

        imports_code = "\n".join(f"import mod{i}" for i in range(20))
        (tmp_path / "main.py").write_text(imports_code)
        for i in range(20):
            (tmp_path / f"mod{i}.py").write_text(f"VAL = {i}\n")

        graph = ImportGraph(tmp_path)
        imports = graph.first_degree_imports("main.py", limit=5)
        assert len(imports) <= 5

    def test_unknown_file_returns_empty(self, tmp_path):
        from safecode.index.import_graph import ImportGraph

        graph = ImportGraph(tmp_path)
        assert graph.first_degree_imports("nonexistent.py") == []

    def test_sensitive_path_via_import_graph(self, tmp_path):
        from safecode.index.import_graph import ImportGraph

        (tmp_path / "main.py").write_text("from config import secret\n")
        # The import resolver only returns files that exist — .env would not match .py
        graph = ImportGraph(tmp_path)
        imports = graph.first_degree_imports("main.py")
        # config.py doesn't exist, so result should be empty
        assert len(imports) == 0


# ---------------------------------------------------------------------------
# ContextCollector.collect() with seed_files (v5.3.0)
# ---------------------------------------------------------------------------

class TestContextCollectorSeedFiles:
    def test_collect_with_seed_files_adds_import_context(self, tmp_path):
        from safecode.context.collector import ContextCollector

        (tmp_path / "main.py").write_text("from utils import helper\n")
        (tmp_path / "utils.py").write_text("def helper(): return 42\n")

        collector = ContextCollector(tmp_path)
        ctx = collector.collect(query="test", seed_files=["main.py"])
        assert "import_context" in ctx

    def test_collect_without_seed_files_no_import_context(self, tmp_path):
        from safecode.context.collector import ContextCollector

        collector = ContextCollector(tmp_path)
        ctx = collector.collect(query="test")
        assert "import_context" not in ctx

    def test_import_context_snippets_populated(self, tmp_path):
        from safecode.context.collector import ContextCollector

        (tmp_path / "main.py").write_text("from utils import helper\n")
        (tmp_path / "utils.py").write_text("def helper(): return 42\n")

        collector = ContextCollector(tmp_path)
        ctx = collector.collect(seed_files=["main.py"])
        imp_ctx = ctx.get("import_context", {})
        assert "seeds" in imp_ctx
        assert "main.py" in imp_ctx["seeds"]


# ---------------------------------------------------------------------------
# GitContext.to_context_block (v5.3.0)
# ---------------------------------------------------------------------------

class TestGitContextBlock:
    def test_empty_context_returns_empty_string(self):
        from safecode.context.git_context import GitContext
        ctx = GitContext()
        assert ctx.to_context_block() == ""

    def test_error_context_returns_empty_string(self):
        from safecode.context.git_context import GitContext
        ctx = GitContext(error="git not found")
        assert ctx.to_context_block() == ""

    def test_context_with_commits_renders_section(self):
        from safecode.context.git_context import GitContext, CommitInfo
        ctx = GitContext(
            recent_commits=[
                CommitInfo(hash="abc12345", subject="fix auth bug", author="dev@example.com",
                           files_changed=["src/auth.py"]),
            ]
        )
        block = ctx.to_context_block()
        assert "Recent commits" in block
        assert "abc1234" in block
        assert "fix auth bug" in block

    def test_context_bounded_to_max_chars(self):
        from safecode.context.git_context import GitContext, CommitInfo, _MAX_CONTEXT_CHARS
        # Create context with many commits
        commits = [
            CommitInfo(hash=f"hash{i:04d}", subject=f"commit {'x' * 100}", author="dev",
                       files_changed=[f"file{i}.py"])
            for i in range(50)
        ]
        ctx = GitContext(recent_commits=commits)
        block = ctx.to_context_block()
        assert len(block) <= _MAX_CONTEXT_CHARS

    def test_branch_diff_files_rendered(self):
        from safecode.context.git_context import GitContext
        ctx = GitContext(branch_diff_files=["src/auth.py", "tests/test_auth.py"])
        block = ctx.to_context_block()
        assert "src/auth.py" in block
        assert "tests/test_auth.py" in block


# ---------------------------------------------------------------------------
# GitContextCollector (integration — uses real git or graceful failure)
# ---------------------------------------------------------------------------

class TestGitContextCollector:
    def test_collect_in_non_git_dir_returns_error(self, tmp_path):
        from safecode.context.git_context import GitContextCollector
        collector = GitContextCollector(tmp_path)
        ctx = collector.collect()
        # Either error (not a git repo) or empty (git not available)
        assert ctx.error is not None or ctx.is_empty()

    def test_collect_in_git_repo_does_not_crash(self, tmp_path):
        """Collection in a git repo (this project) should not raise."""
        from safecode.context.git_context import collect_git_context
        from pathlib import Path
        # Use the actual project root (is a git repo)
        project_root = Path(__file__).parent.parent
        ctx = collect_git_context(project_root)
        # Should not crash; may have data or graceful empty
        assert ctx is not None
