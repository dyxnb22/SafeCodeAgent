"""Verify Enterprise planning documents exist and are indexed."""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent

PRODUCT_PLANNING_DOCS = [
    "product-planning/version-roadmap.md",
    "product-planning/post-ga-portfolio-roadmap.md",
    "product-planning/milestone-acceptance.md",
    "product-planning/execution-backlog.md",
    "product-planning/interview-master-narrative.md",
    "product-planning/case-study-secure-change-platform.md",
    "product-planning/decision-log.md",
    "product-planning/claude-code-execution-guide.md",
]

ENTERPRISE_DOCS = [
    "enterprise-docs/system-architecture-v1.md",
    "enterprise-docs/data-models.md",
    "enterprise-docs/workflow-design.md",
    "enterprise-docs/rag-implementation-plan.md",
    "enterprise-docs/security-governance-plan.md",
    "enterprise-docs/evaluation-plan.md",
    "enterprise-docs/agentops-observability-plan.md",
    "enterprise-docs/deployment-profiles.md",
    "enterprise-docs/security-review-v2-0.md",
    "enterprise-docs/platform-architecture-v2.md",
    "enterprise-docs/security/external-gates.md",
]

ALL_PLANNING_DOCS = PRODUCT_PLANNING_DOCS + ENTERPRISE_DOCS

PRODUCT_PLANNING_README_FILES = [
    "version-roadmap.md",
    "post-ga-portfolio-roadmap.md",
    "milestone-acceptance.md",
    "execution-backlog.md",
    "interview-master-narrative.md",
    "case-study-secure-change-platform.md",
    "decision-log.md",
    "claude-code-execution-guide.md",
]

ENTERPRISE_README_FILES = [
    "system-architecture-v1.md",
    "data-models.md",
    "workflow-design.md",
    "rag-implementation-plan.md",
    "security-governance-plan.md",
    "evaluation-plan.md",
    "agentops-observability-plan.md",
    "deployment-profiles.md",
    "security-review-v2-0.md",
    "platform-architecture-v2.md",
    "security/external-gates.md",
]


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line
    return ""


@pytest.mark.parametrize("relative_path", ALL_PLANNING_DOCS)
def test_planning_document_exists_with_h1(relative_path: str) -> None:
    path = _ROOT / relative_path
    assert path.is_file(), f"missing planning document: {relative_path}"

    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"planning document is empty: {relative_path}"

    first_line = _first_non_empty_line(text)
    assert first_line.startswith("# "), (
        f"first non-empty line must be an H1 in {relative_path}: {first_line!r}"
    )


def test_product_planning_readme_indexes_new_docs() -> None:
    readme = (_ROOT / "product-planning/README.md").read_text(encoding="utf-8")
    for filename in PRODUCT_PLANNING_README_FILES:
        assert filename in readme, (
            f"product-planning/README.md must reference {filename}"
        )


def test_enterprise_docs_readme_indexes_new_docs() -> None:
    readme = (_ROOT / "enterprise-docs/README.md").read_text(encoding="utf-8")
    for filename in ENTERPRISE_README_FILES:
        assert filename in readme, (
            f"enterprise-docs/README.md must reference {filename}"
        )
