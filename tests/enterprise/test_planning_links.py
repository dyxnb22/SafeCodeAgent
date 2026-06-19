"""Verify local links and path references across portfolio documentation surfaces."""

from __future__ import annotations

import pytest

from tests.enterprise.markdown_doc_scan import (
    documentation_surface_paths,
    internal_markdown_target_exists,
    iter_backtick_path_references,
    iter_internal_markdown_link_targets,
    path_exists_in_repo,
    repo_root,
)

_ROOT = repo_root()


def test_documentation_surface_inventory_is_nonempty() -> None:
    surfaces = documentation_surface_paths()
    assert len(surfaces) >= 10
    assert "README.md" in surfaces
    assert any(path.startswith("enterprise-docs/") for path in surfaces)
    assert any(path.startswith("product-planning/") for path in surfaces)
    assert any(path.startswith(".agents/") for path in surfaces)


@pytest.mark.parametrize("relative_doc", documentation_surface_paths())
def test_documentation_markdown_links_resolve(relative_doc: str) -> None:
    doc_path = _ROOT / relative_doc
    text = doc_path.read_text(encoding="utf-8")
    missing: list[str] = []
    for target in iter_internal_markdown_link_targets(text):
        if internal_markdown_target_exists(doc_path, target):
            continue
        missing.append(f"{relative_doc}: {target}")
    assert not missing, "broken Markdown links:\n" + "\n".join(missing)


@pytest.mark.parametrize("relative_doc", documentation_surface_paths())
def test_documentation_backtick_paths_exist(relative_doc: str) -> None:
    doc_path = _ROOT / relative_doc
    missing: list[str] = []
    text = doc_path.read_text(encoding="utf-8")
    for ref in sorted(iter_backtick_path_references(text)):
        if path_exists_in_repo(ref):
            continue
        missing.append(f"{relative_doc}: {ref}")
    assert not missing, "missing backtick path references:\n" + "\n".join(missing)


def test_architecture_poster_exists() -> None:
    poster = _ROOT / "docs/architecture-poster.md"
    assert poster.is_file()
    assert poster.read_text(encoding="utf-8").startswith("# ")


def test_planning_readme_index_paths_exist() -> None:
    """Keep explicit coverage for the planning index document."""
    planning_readme = _ROOT / "product-planning/README.md"
    assert planning_readme.is_file()
    missing = [
        ref
        for ref in iter_backtick_path_references(planning_readme.read_text(encoding="utf-8"))
        if not path_exists_in_repo(ref)
    ]
    assert not missing


def test_markdown_links_resolve_relative_to_containing_document() -> None:
    document = _ROOT / "enterprise-docs" / "README.md"
    assert internal_markdown_target_exists(document, "platform-architecture-v2.md")
    assert not internal_markdown_target_exists(document, "RELEASE-NOTES-v3.0.0.md")


def test_document_paths_cannot_escape_repository() -> None:
    document = _ROOT / "enterprise-docs" / "README.md"
    assert not internal_markdown_target_exists(document, "../../../../etc/passwd")
    assert not path_exists_in_repo("../../../../etc/passwd")


def test_backtick_scan_skips_only_legacy_clause() -> None:
    refs = iter_backtick_path_references(
        "Legacy `src/old.py` is no longer maintained; use `src/safecode/cli.py`."
    )
    assert "src/old.py" not in refs
    assert "src/safecode/cli.py" in refs


def test_backtick_scan_skips_templates_but_keeps_concrete_paths() -> None:
    refs = iter_backtick_path_references(
        "Compare `tests/<domain>/test_*.py` with `tests/enterprise/test_readme_links.py`."
    )
    assert refs == {"tests/enterprise/test_readme_links.py"}
