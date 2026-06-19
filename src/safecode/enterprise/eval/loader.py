"""Enterprise evaluation case loader."""

from __future__ import annotations

from pathlib import Path

import yaml

from safecode.enterprise.eval.cases import EvaluationCase
from safecode.enterprise.eval.exceptions import DuplicateCaseIdError, InvalidEvalCaseError


def load_case_file(path: Path) -> EvaluationCase:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise InvalidEvalCaseError(f"invalid eval case file: {path}")
    try:
        return EvaluationCase.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - surface as InvalidEvalCaseError
        raise InvalidEvalCaseError(f"invalid eval case {path}: {exc}") from exc


def discover_case_files(cases_root: Path, *, suite: str | None = None) -> list[Path]:
    if suite is not None:
        target = cases_root / suite
        if not target.is_dir():
            return []
        return sorted(target.glob("*.yaml"))
    paths: list[Path] = []
    if not cases_root.is_dir():
        return paths
    for suite_dir in sorted(cases_root.iterdir()):
        if suite_dir.is_dir():
            paths.extend(sorted(suite_dir.glob("*.yaml")))
    return paths


def discover_cases(cases_root: Path, *, suite: str | None = None) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    seen: dict[str, Path] = {}
    for path in discover_case_files(cases_root, suite=suite):
        case = load_case_file(path)
        if case.case_id in seen:
            raise DuplicateCaseIdError(
                f"duplicate case_id {case.case_id!r} in {path} and {seen[case.case_id]}"
            )
        seen[case.case_id] = path
        cases.append(case)
    return cases
