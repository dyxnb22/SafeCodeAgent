"""Fixture loader for task eval fixtures (v2.5.0).

Loads and validates TaskEvalFixture instances from JSON files or raw dicts.
JSON is the canonical on-disk format; it is consistent with the project's
existing state-file conventions and requires no additional dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from safecode.eval.fixtures import TaskEvalFixture


SUPPORTED_EXTENSIONS = frozenset({".json"})


class FixtureLoadError(ValueError):
    """Raised when a fixture file cannot be loaded or fails validation.

    Always a subclass of ValueError so callers that catch ValueError will
    also catch fixture load failures — consistent with the rest of the
    codebase's error hierarchy.
    """


def load_fixture(path: Path) -> TaskEvalFixture:
    """Load and validate a TaskEvalFixture from a JSON file.

    Args:
        path: Path to the fixture JSON file.

    Returns:
        A validated TaskEvalFixture instance.

    Raises:
        FixtureLoadError: If the file does not exist, cannot be parsed,
            has an unsupported extension, or fails Pydantic validation.
    """
    if not path.exists():
        raise FixtureLoadError(f"Fixture file not found: {path}")
    if not path.is_file():
        raise FixtureLoadError(f"Fixture path is not a regular file: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise FixtureLoadError(
            f"Unsupported fixture format {suffix!r} for {path.name}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FixtureLoadError(f"Cannot read fixture {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FixtureLoadError(f"Fixture {path} contains invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise FixtureLoadError(
            f"Fixture {path} must be a JSON object, got {type(data).__name__!r}."
        )
    return _validate(data, source=str(path))


def load_fixture_from_dict(data: dict) -> TaskEvalFixture:
    """Validate and construct a TaskEvalFixture from a raw Python dict.

    Useful in tests and for programmatic fixture construction without
    writing a file to disk.

    Args:
        data: Raw fixture data as a Python dict.

    Returns:
        A validated TaskEvalFixture instance.

    Raises:
        FixtureLoadError: If the dict fails Pydantic validation.
    """
    if not isinstance(data, dict):
        raise FixtureLoadError(
            f"Expected a dict, got {type(data).__name__!r}."
        )
    return _validate(data, source="<dict>")


def load_fixtures_from_dir(directory: Path) -> list[TaskEvalFixture]:
    """Load all JSON fixtures from a directory (non-recursive).

    Files that cannot be loaded are collected into a single FixtureLoadError
    raised after scanning all files, so callers see the full list of problems.

    Args:
        directory: Directory containing ``*.json`` fixture files.

    Returns:
        List of validated TaskEvalFixture instances, sorted by fixture name.

    Raises:
        FixtureLoadError: If the directory does not exist or any fixture fails.
    """
    if not directory.exists():
        raise FixtureLoadError(f"Fixture directory not found: {directory}")
    if not directory.is_dir():
        raise FixtureLoadError(f"Fixture path is not a directory: {directory}")

    fixtures: list[TaskEvalFixture] = []
    errors: list[str] = []

    for path in sorted(directory.glob("*.json")):
        try:
            fixtures.append(load_fixture(path))
        except FixtureLoadError as exc:
            errors.append(str(exc))

    if errors:
        joined = "\n  ".join(errors)
        raise FixtureLoadError(
            f"Failed to load {len(errors)} fixture(s) from {directory}:\n  {joined}"
        )

    fixtures.sort(key=lambda f: f.name)
    return fixtures


def _validate(data: dict, source: str) -> TaskEvalFixture:
    try:
        return TaskEvalFixture.model_validate(data)
    except ValidationError as exc:
        raise FixtureLoadError(f"Invalid fixture {source}:\n{exc}") from exc
