"""Tests for Python code loader (v1.1.1-T4)."""

from pathlib import Path

from safecode.enterprise.rag.loaders.loader_code import load_code_source
from safecode.enterprise.rag.source_registry import KnowledgeSource, SourceType

_SOURCE = KnowledgeSource(
    source_id="code-app",
    source_type=SourceType.code,
    name="App",
    path_or_uri="app.py",
    owner="dev",
    permission_scope=["org"],
    refresh_cadence="on_demand",
    parser="code",
)


def test_emits_records_for_top_level_defs(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def fetch_user(user_id: str):\n    return user_id\n\n"
        "class Repo:\n    def list_users(self):\n        return []\n",
        encoding="utf-8",
    )
    result = load_code_source(_SOURCE, tmp_path)
    names = {record.metadata["symbol_name"] for record in result.records}
    assert names == {"fetch_user", "Repo"}


def test_skips_files_larger_than_two_mb_with_warning(tmp_path: Path):
    big_path = tmp_path / "big.py"
    big_path.write_text("def big():\n    pass\n", encoding="utf-8")
    with big_path.open("ab") as handle:
        handle.write(b"#" * (2 * 1024 * 1024))

    source = _SOURCE.model_copy(update={"path_or_uri": "big.py"})
    result = load_code_source(source, tmp_path)
    assert result.records == []
    assert result.events and result.events[0].kind == "warning"


def test_loads_python_files_from_directory(tmp_path: Path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "module.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (pkg / "notes.txt").write_text("not code", encoding="utf-8")
    source = _SOURCE.model_copy(update={"path_or_uri": "pkg"})
    result = load_code_source(source, tmp_path)
    assert len(result.records) == 1
    assert result.records[0].metadata["symbol_name"] == "helper"
