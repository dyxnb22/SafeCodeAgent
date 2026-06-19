"""Disposable isolated workspaces for Enterprise eval runners."""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from safecode.enterprise.eval.cases import EvaluationCase
from safecode.enterprise.eval.exceptions import InvalidEvalCaseError
from safecode.utils.paths import resolve_inside_root

_ENTERPRISE_REL = Path("examples/enterprise")
_SUPPORT_FILES = ("knowledge_sources.yaml",)
_SUPPORT_DIRS = ("policies", "sample_app", "scanner_findings", "runbooks")


def _require_relative_fixture_ref(case: EvaluationCase) -> Path:
    raw = case.input_fixture or ""
    if not raw or "\\" in raw or raw in {".", ".."}:
        raise InvalidEvalCaseError(
            f"eval case {case.case_id!r} input_fixture must be a project-relative path"
        )
    fixture_ref = Path(raw)
    if fixture_ref.is_absolute() or ".." in fixture_ref.parts or "." in fixture_ref.parts:
        raise InvalidEvalCaseError(
            f"eval case {case.case_id!r} input_fixture must be a project-relative path"
        )
    return fixture_ref


def _require_inside(root: Path, path: Path, *, label: str) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise InvalidEvalCaseError(f"{label} escapes its allowed root") from exc
    return resolved


def _validate_source_tree(project_root: Path, source: Path) -> None:
    """Reject fixture/support symlinks that resolve outside the project root."""
    root = project_root.resolve()
    candidates = [source]
    if source.is_dir():
        candidates.extend(source.rglob("*"))
    for candidate in candidates:
        if not candidate.is_symlink():
            continue
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise InvalidEvalCaseError(
                f"eval source symlink escapes project root: {candidate.relative_to(root)}"
            ) from exc


def _copy_path(
    source: Path,
    target: Path,
    *,
    project_root: Path,
    workspace: Path,
) -> None:
    _require_inside(project_root, source, label="eval source")
    _require_inside(workspace, target, label="eval workspace target")
    _validate_source_tree(project_root, source)
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _copy_enterprise_support(project_root: Path, workspace: Path) -> None:
    enterprise_src = project_root / _ENTERPRISE_REL
    enterprise_dst = workspace / _ENTERPRISE_REL
    enterprise_dst.mkdir(parents=True, exist_ok=True)
    for name in _SUPPORT_FILES:
        src_file = enterprise_src / name
        if src_file.is_file():
            _copy_path(
                src_file,
                enterprise_dst / name,
                project_root=project_root,
                workspace=workspace,
            )
    for dir_name in _SUPPORT_DIRS:
        src_dir = enterprise_src / dir_name
        if src_dir.is_dir():
            _copy_path(
                src_dir,
                enterprise_dst / dir_name,
                project_root=project_root,
                workspace=workspace,
            )


def stage_eval_workspace(project_root: Path, case: EvaluationCase, workspace: Path) -> str:
    """Populate *workspace* with eval assets and return the workflow ``input_ref``."""
    fixture_rel = _require_relative_fixture_ref(case)
    try:
        fixture_source = resolve_inside_root(project_root, fixture_rel)
    except PermissionError as exc:
        raise InvalidEvalCaseError(
            f"eval case {case.case_id!r} input_fixture escapes project root"
        ) from exc
    if case.suite == "remediation":
        case_dir = workspace / "case"
        if case_dir.exists():
            shutil.rmtree(case_dir)
        _copy_path(
            fixture_source,
            case_dir,
            project_root=project_root,
            workspace=workspace,
        )
        _copy_enterprise_support(project_root, workspace)
        return "case"

    if fixture_source.exists():
        _copy_path(
            fixture_source,
            workspace / fixture_rel,
            project_root=project_root,
            workspace=workspace,
        )
    _copy_enterprise_support(project_root, workspace)
    return fixture_rel.as_posix()


@contextmanager
def isolated_eval_workspace(
    project_root: Path,
    case: EvaluationCase,
) -> Iterator[tuple[Path, str]]:
    """Yield ``(workspace_root, input_ref)`` inside an auto-cleaned temp directory."""
    container = Path(tempfile.mkdtemp(prefix="sac-eval-"))
    workspace = container / "workspace"
    workspace.mkdir(parents=True)
    try:
        input_ref = stage_eval_workspace(project_root, case, workspace)
        yield workspace, input_ref
    finally:
        shutil.rmtree(container, ignore_errors=True)
