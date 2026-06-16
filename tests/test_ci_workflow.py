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


def test_main_test_job_does_not_run_preflight() -> None:
    """The main 'test' CI job must not run release preflight or git tag checks.
    Preflight lives in the dedicated 'release' job (v5.5.0) which only fires on tags.
    """
    import yaml
    data = yaml.safe_load(_workflow_text())
    test_job = data["jobs"]["test"]
    steps_text = str(test_job["steps"])
    assert "release preflight" not in steps_text
    assert "git describe --exact-match" not in steps_text


def test_ci_generates_changelog_preview() -> None:
    text = _workflow_text()
    assert "release changelog" in text
    assert "--recent 5" in text
    assert "--from 2.6.14 --to 2.6.17" not in text
