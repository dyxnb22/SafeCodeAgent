"""Tests for v2.6.17 CI workflow draft."""

from pathlib import Path


WORKFLOW = Path(".github/workflows/ci.yml")


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_ci_workflow_exists() -> None:
    assert WORKFLOW.is_file()


def test_ci_runs_full_regression() -> None:
    text = _workflow_text()
    assert "PYTHONPATH=src python3 -m pytest -q" in text


def test_ci_runs_release_smoke_and_meta() -> None:
    text = _workflow_text()
    assert "release smoke" in text
    assert "release meta" in text


def test_ci_does_not_require_exact_tag_release_check_or_preflight() -> None:
    text = _workflow_text()
    assert "release check" not in text
    assert "release preflight" not in text
    assert "git describe --exact-match" not in text


def test_ci_generates_changelog_preview() -> None:
    text = _workflow_text()
    assert "release changelog" in text
    assert "--from 2.6.14 --to 2.6.17" in text
