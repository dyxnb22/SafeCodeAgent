"""Tests for v4.6.1 pinned files in context selection."""

from __future__ import annotations

from pathlib import Path

from safecode.context.collector import ContextCollector
from safecode.context.selector import ContextSelector
from safecode.memory.facade import MemoryFacade


def test_pinned_file_is_included_even_without_keyword_match(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "billing.py").write_text("", encoding="utf-8")
    (tmp_path / "docs.md").write_text("", encoding="utf-8")
    MemoryFacade(tmp_path).pin_file("docs.md")

    sources = ContextSelector(tmp_path).select_sources("billing", limit=4)

    assert "docs.md" in [source.path for source in sources]
    assert any(source.reason == "pinned file" for source in sources)


def test_pinned_quota_is_enforced(tmp_path: Path) -> None:
    for index in range(10):
        (tmp_path / f"pinned_{index}.py").write_text("", encoding="utf-8")
        MemoryFacade(tmp_path).pin_file(f"pinned_{index}.py")
    for index in range(10):
        (tmp_path / f"billing_{index}.py").write_text("", encoding="utf-8")

    sources = ContextSelector(tmp_path).select_sources("billing", limit=8)
    pinned = [source for source in sources if source.reason == "pinned file"]

    assert len(pinned) == 2
    assert any(source.path.startswith("billing_") for source in sources)


def test_missing_pinned_file_warning_is_deterministic(tmp_path: Path) -> None:
    MemoryFacade(tmp_path).pin_file("missing.py")
    selector = ContextSelector(tmp_path)

    sources = selector.select_sources("anything", limit=4)

    assert sources == []
    assert selector.last_warnings == {"pinned_missing": ["missing.py"]}


def test_collector_surfaces_pinned_missing_warning(tmp_path: Path) -> None:
    MemoryFacade(tmp_path).pin_file("missing.py")

    context = ContextCollector(tmp_path).collect("billing")

    assert context["selected_context"]["warnings"]["pinned_missing"] == ["missing.py"]


def test_ignored_sensitive_and_binary_pins_are_excluded(tmp_path: Path) -> None:
    (tmp_path / ".sac").mkdir()
    (tmp_path / ".sac" / "internal.py").write_text("", encoding="utf-8")
    (tmp_path / ".env").write_text("TOKEN=value\n", encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02")
    (tmp_path / "billing.py").write_text("", encoding="utf-8")
    facade = MemoryFacade(tmp_path)
    facade.pin_file(".sac/internal.py")
    facade.pin_file(".env")
    facade.pin_file("binary.bin")

    sources = ContextSelector(tmp_path).select_sources("billing", limit=5)

    paths = [source.path for source in sources]
    assert ".sac/internal.py" not in paths
    assert ".env" not in paths
    assert "binary.bin" not in paths


def test_pinned_paths_cannot_escape_project_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"

    try:
        MemoryFacade(tmp_path).pin_file(outside)
    except ValueError as exc:
        assert "project root" in str(exc)
    else:
        raise AssertionError("expected root escape refusal")
