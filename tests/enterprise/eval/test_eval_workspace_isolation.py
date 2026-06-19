"""Eval workspace isolation tests for PR review and remediation suites."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from safecode.enterprise.eval.cases import EvaluationCase
from safecode.enterprise.eval.exceptions import InvalidEvalCaseError
from safecode.enterprise.eval.loader import discover_cases
from safecode.enterprise.eval.runner import run_suite
from safecode.enterprise.eval.workspace import isolated_eval_workspace, stage_eval_workspace

_ROOT = Path(__file__).resolve().parents[3]
_CASES = Path(__file__).resolve().parent / "cases"


def _tree_digest(root: Path) -> str:
    if not root.exists():
        return ""
    digest = hashlib.sha256()
    for item in sorted(path for path in root.rglob("*")):
        rel = str(item.relative_to(root)).encode("utf-8")
        digest.update(rel)
        if item.is_file():
            digest.update(item.read_bytes())
    return digest.hexdigest()


def _fixture_tree_digest(project_root: Path, suite: str) -> str:
    digest = hashlib.sha256()
    cases = discover_cases(_CASES, suite=suite)
    for case in cases:
        fixture = project_root / (case.input_fixture or "")
        digest.update(_tree_digest(fixture).encode("utf-8"))
    return digest.hexdigest()


def test_pr_review_suite_passes_twice_in_same_process():
    cases = discover_cases(_CASES, suite="pr_review")
    for _ in range(2):
        results = run_suite(cases, project_root=_ROOT)
        assert len(results) == 5
        failures = [item.case_id for item in results if not item.passed]
        assert not failures, failures


def test_remediation_suite_passes_twice_in_same_process():
    cases = discover_cases(_CASES, suite="remediation")
    for _ in range(2):
        results = run_suite(cases, project_root=_ROOT)
        assert len(results) == 5
        failures = [item.case_id for item in results if not item.passed]
        assert not failures, failures


def test_pr_review_eval_ignores_corrupt_project_root_sac(tmp_path: Path):
    sentinel = tmp_path / ".sac" / "sentinel.txt"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("corrupt-audit-chain-head: not-valid\n", encoding="utf-8")
    (tmp_path / ".sac" / "audit").mkdir()
    (tmp_path / ".sac" / "audit" / "events.jsonl").write_text(
        '{"broken": true}\n',
        encoding="utf-8",
    )
    examples = _ROOT / "examples"
    if examples.is_dir():
        dest = tmp_path / "examples"
        dest.mkdir(parents=True)
        for item in examples.iterdir():
            if item.name == "enterprise":
                continue
            if item.is_dir():
                shutil.copytree(item, dest / item.name)
        shutil.copytree(examples / "enterprise", dest / "enterprise")

    sac_before = _tree_digest(tmp_path / ".sac")
    fixture_before = _fixture_tree_digest(tmp_path, "pr_review")
    cases = discover_cases(_CASES, suite="pr_review")
    results = run_suite(cases, project_root=tmp_path)
    assert all(item.passed for item in results), [
        (item.case_id, item.notes, item.safety_assertion_failures) for item in results if not item.passed
    ]
    assert _tree_digest(tmp_path / ".sac") == sac_before
    assert sentinel.read_text(encoding="utf-8") == "corrupt-audit-chain-head: not-valid\n"
    assert _fixture_tree_digest(tmp_path, "pr_review") == fixture_before


def test_remediation_eval_ignores_corrupt_project_root_sac(tmp_path: Path):
    sentinel = tmp_path / ".sac" / "sentinel.txt"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("do-not-touch\n", encoding="utf-8")
    examples = _ROOT / "examples"
    if examples.is_dir():
        dest = tmp_path / "examples"
        dest.mkdir(parents=True)
        shutil.copytree(examples / "enterprise", dest / "enterprise")

    sac_before = _tree_digest(tmp_path / ".sac")
    fixture_before = _fixture_tree_digest(tmp_path, "remediation")
    cases = discover_cases(_CASES, suite="remediation")
    results = run_suite(cases, project_root=tmp_path)
    assert all(item.passed for item in results), [
        (item.case_id, item.notes, item.metrics) for item in results if not item.passed
    ]
    assert _tree_digest(tmp_path / ".sac") == sac_before
    assert sentinel.read_text(encoding="utf-8") == "do-not-touch\n"
    assert _fixture_tree_digest(tmp_path, "remediation") == fixture_before


@pytest.mark.parametrize("suite", ["pr_review", "remediation"])
@pytest.mark.parametrize(
    "fixture_ref",
    ["../outside.txt", "/tmp/outside.txt", ".", r"..\outside"],
)
def test_eval_workspace_rejects_non_relative_fixture_paths(
    tmp_path: Path,
    suite: str,
    fixture_ref: str,
):
    project_root = tmp_path / "project"
    workspace = tmp_path / "container" / "workspace"
    project_root.mkdir()
    workspace.mkdir(parents=True)
    victim = workspace.parent / "outside.txt"
    victim.write_text("do-not-overwrite", encoding="utf-8")
    case = EvaluationCase(
        case_id=f"{suite}.path_escape",
        suite=suite,
        goal="Path-boundary regression probe.",
        input_fixture=fixture_ref,
    )

    with pytest.raises(InvalidEvalCaseError, match="project-relative path"):
        stage_eval_workspace(project_root, case, workspace)

    assert victim.read_text(encoding="utf-8") == "do-not-overwrite"


@pytest.mark.parametrize("suite", ["pr_review", "remediation"])
def test_eval_workspace_rejects_fixture_symlink_escape(tmp_path: Path, suite: str):
    project_root = tmp_path / "project"
    workspace = tmp_path / "container" / "workspace"
    outside = tmp_path / "outside"
    project_root.mkdir()
    workspace.mkdir(parents=True)
    outside.mkdir()
    (outside / "fixture.json").write_text("{}", encoding="utf-8")
    (project_root / "fixture-link").symlink_to(outside, target_is_directory=True)
    case = EvaluationCase(
        case_id=f"{suite}.symlink_escape",
        suite=suite,
        goal="Symlink-boundary regression probe.",
        input_fixture="fixture-link",
    )

    with pytest.raises(InvalidEvalCaseError, match="escapes project root"):
        stage_eval_workspace(project_root, case, workspace)


def test_eval_workspace_rejects_nested_symlink_escape(tmp_path: Path):
    project_root = tmp_path / "project"
    workspace = tmp_path / "container" / "workspace"
    fixture = project_root / "fixture"
    project_root.mkdir()
    workspace.mkdir(parents=True)
    fixture.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("outside", encoding="utf-8")
    (fixture / "leak.txt").symlink_to(outside)
    case = EvaluationCase(
        case_id="pr_review.nested_symlink_escape",
        suite="pr_review",
        goal="Nested symlink-boundary regression probe.",
        input_fixture="fixture",
    )

    with pytest.raises(InvalidEvalCaseError, match="symlink escapes project root"):
        stage_eval_workspace(project_root, case, workspace)


def test_eval_workspace_cleans_container_when_staging_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    container = tmp_path / "owned-container"
    case = EvaluationCase(
        case_id="pr_review.cleanup_after_failure",
        suite="pr_review",
        goal="Cleanup regression probe.",
        input_fixture="../outside.txt",
    )
    monkeypatch.setattr(
        "safecode.enterprise.eval.workspace.tempfile.mkdtemp",
        lambda **_: str(container),
    )

    with pytest.raises(InvalidEvalCaseError):
        with isolated_eval_workspace(tmp_path, case):
            pytest.fail("invalid fixture path must fail before yielding")

    assert not container.exists()


def test_eval_workspace_accepts_inside_root_symlink_fixture(tmp_path: Path):
    project_root = tmp_path / "project"
    workspace = tmp_path / "container" / "workspace"
    fixture_dir = project_root / "examples" / "enterprise" / "fixtures" / "pr_sql_injection"
    project_root.mkdir(parents=True)
    workspace.mkdir(parents=True)
    fixture_dir.parent.mkdir(parents=True)
    shutil.copytree(_ROOT / "examples" / "enterprise" / "fixtures" / "pr_sql_injection", fixture_dir)
    link = project_root / "fixture-link"
    link.symlink_to(fixture_dir, target_is_directory=True)
    case = EvaluationCase(
        case_id="pr_review.inside_symlink",
        suite="pr_review",
        goal="Accept in-root symlink fixture.",
        input_fixture="fixture-link",
    )

    input_ref = stage_eval_workspace(project_root, case, workspace)

    assert input_ref == "fixture-link"
    assert (workspace / "fixture-link" / "pr.json").is_file()
