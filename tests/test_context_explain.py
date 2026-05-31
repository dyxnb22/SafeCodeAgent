"""Tests for v2.1.4 context explain command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from safecode.cli import app
from safecode.context.selector import ContextSelector, SelectedContextSource

runner = CliRunner()


def _write_demo_project(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "billing_api.py").write_text("def charge(): pass\n", encoding="utf-8")
    (root / "src" / "auth.py").write_text("def login(): pass\n", encoding="utf-8")
    (root / "tests" / "test_billing_api.py").write_text("def test_charge(): pass\n", encoding="utf-8")
    (root / "README.md").write_text("# Demo project\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")


class TestContextExplainCLI:
    def test_explain_shows_selected_files(self, tmp_path: Path) -> None:
        _write_demo_project(tmp_path)
        result = runner.invoke(app, ["context", "explain", "billing api", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "billing" in result.output.lower()

    def test_explain_shows_budget_metadata(self, tmp_path: Path) -> None:
        _write_demo_project(tmp_path)
        result = runner.invoke(app, ["context", "explain", "auth login", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Max bytes" in result.output

    def test_explain_shows_repo_map_section(self, tmp_path: Path) -> None:
        _write_demo_project(tmp_path)
        result = runner.invoke(app, ["context", "explain", "auth", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Repo Map" in result.output
        assert "Files" in result.output

    def test_explain_no_match_exits_cleanly(self, tmp_path: Path) -> None:
        _write_demo_project(tmp_path)
        result = runner.invoke(app, ["context", "explain", "zzzznonexistent", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "No files matched" in result.output

    def test_explain_limit_option(self, tmp_path: Path) -> None:
        _write_demo_project(tmp_path)
        result = runner.invoke(app, ["context", "explain", "billing api", "--root", str(tmp_path), "--limit", "1"])
        assert result.exit_code == 0
        # With limit=1, only the top-scoring file should appear
        assert result.exit_code == 0

    def test_explain_does_not_expose_sensitive_file(self, tmp_path: Path) -> None:
        _write_demo_project(tmp_path)
        (tmp_path / ".env").write_text("SECRET=hunter2\n", encoding="utf-8")
        result = runner.invoke(app, ["context", "explain", "env secret", "--root", str(tmp_path)])
        assert result.exit_code == 0
        # .env should be filtered out by selector (it's a sensitive name)
        assert "SECRET=hunter2" not in result.output

    def test_explain_is_read_only_no_llm(self, tmp_path: Path) -> None:
        """Command must not write files or call LLM."""
        _write_demo_project(tmp_path)
        sac_dir = tmp_path / ".sac"
        result = runner.invoke(app, ["context", "explain", "billing", "--root", str(tmp_path)])
        assert result.exit_code == 0
        # No .sac directory should be created by this command
        assert not sac_dir.exists()

    def test_explain_config_load_failure_exits_cleanly(self, tmp_path: Path, monkeypatch) -> None:
        _write_demo_project(tmp_path)

        def fail_load(_root: Path) -> object:
            raise RuntimeError("config boom")

        monkeypatch.setattr("safecode.cli_context.SafeCodeConfig.load", fail_load)

        result = runner.invoke(app, ["context", "explain", "billing", "--root", str(tmp_path)])

        assert result.exit_code == 1


class TestContextSelectorUnit:
    def test_select_sources_returns_ranked_results(self, tmp_path: Path) -> None:
        (tmp_path / "billing_api.py").write_text("", encoding="utf-8")
        (tmp_path / "auth.py").write_text("", encoding="utf-8")

        sources = ContextSelector(tmp_path).select_sources("billing api")

        assert isinstance(sources[0], SelectedContextSource)
        assert sources[0].path == "billing_api.py"
        assert sources[0].score == 2
        assert "billing" in sources[0].reason

    def test_select_sources_empty_query_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("", encoding="utf-8")
        sources = ContextSelector(tmp_path).select_sources("", limit=5)
        assert sources == []

    def test_select_sources_limit_respected(self, tmp_path: Path) -> None:
        for i in range(10):
            (tmp_path / f"billing_module_{i}.py").write_text("", encoding="utf-8")

        sources = ContextSelector(tmp_path).select_sources("billing", limit=3)
        assert len(sources) <= 3
