"""Verify internal Markdown links in the root README."""

from __future__ import annotations

from tests.enterprise.markdown_doc_scan import (
    internal_markdown_target_exists,
    iter_internal_markdown_link_targets,
    repo_root,
)

README = repo_root() / "README.md"


def test_readme_internal_links_resolve() -> None:
    text = README.read_text(encoding="utf-8")
    missing: list[str] = []
    for target in iter_internal_markdown_link_targets(text):
        if internal_markdown_target_exists(README, target):
            continue
        missing.append(target)
    assert not missing, "README broken internal links:\n" + "\n".join(missing)
