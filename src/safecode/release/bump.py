"""Release version bump helper: updates canonical package version locations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from safecode.release.ux import header, next_steps

# Semver-ish: digits and dots only, no leading zeros in segments.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

_PYPROJECT_RE = re.compile(r'^(version\s*=\s*")[^"]+(")', re.MULTILINE)
_INIT_RE = re.compile(r'^(__version__\s*=\s*")[^"]+(")', re.MULTILINE)


@dataclass(frozen=True)
class BumpResult:
    """Result of a version bump operation."""

    new_version: str
    updated_files: list[str]
    skipped_files: list[str]
    errors: list[str]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def _replace_in_file(
    path: Path,
    replacements: list[tuple[re.Pattern[str], str]],
) -> str | None:
    """Apply *pattern* replacement to *path*; return new content or None if no match."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    new_text = text
    changed = False
    for pattern, replacement in replacements:
        new_text, count = pattern.subn(replacement, new_text)
        changed = changed or count > 0
    if not changed:
        return None
    return new_text


def bump_versions(
    new_version: str,
    *,
    project_root: Path | None = None,
    pyproject_path: Path | None = None,
    init_path: Path | None = None,
    test_path: Path | None = None,
    dry_run: bool = False,
) -> BumpResult:
    """Update all canonical package version locations to *new_version*.

    Locations updated:
    - pyproject.toml  [project].version
    - src/safecode/__init__.py  __version__

    Args:
        new_version: target version string, e.g. "2.6.10".
        project_root: repo root; defaults to cwd.
        pyproject_path: override pyproject.toml path.
        init_path: override __init__.py path.
        test_path: ignored; retained for backward-compatible callers.
        dry_run: if True, validate and report without writing files.

    Returns:
        BumpResult with updated/skipped/error lists.
    """
    if not _VERSION_RE.match(new_version):
        return BumpResult(
            new_version=new_version,
            updated_files=[],
            skipped_files=[],
            errors=[
                f"Invalid version {new_version!r}: expected X.Y.Z with numeric segments."
            ],
        )

    root = project_root or Path.cwd()
    pyproj = pyproject_path or (root / "pyproject.toml")
    init = init_path or (root / "src" / "safecode" / "__init__.py")

    targets: list[tuple[Path, list[tuple[re.Pattern[str], str]]]] = [
        (pyproj, [(_PYPROJECT_RE, rf'\g<1>{new_version}\2')]),
        (init, [(_INIT_RE, rf'\g<1>{new_version}\2')]),
    ]

    updated: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for path, replacements in targets:
        if not path.is_file():
            skipped.append(str(path))
            continue
        new_content = _replace_in_file(path, replacements)
        if new_content is None:
            skipped.append(str(path))
        else:
            if not dry_run:
                path.write_text(new_content, encoding="utf-8")
            updated.append(str(path))

    return BumpResult(
        new_version=new_version,
        updated_files=updated,
        skipped_files=skipped,
        errors=errors,
    )


def render_bump_result(result: BumpResult) -> str:
    """Render a BumpResult as human-readable text."""
    lines = header("SafeCode Release Version Bump", result.ok) + [
        f"  target version  : {result.new_version}",
    ]
    if result.errors:
        lines.append("")
        lines.append("Errors:")
        for err in result.errors:
            lines.append(f"  {err}")
        lines.extend(next_steps(["Use a numeric X.Y.Z version, then rerun sac release bump."]))
        return "\n".join(lines)
    lines.append(f"  updated files   : {len(result.updated_files)}")
    for f in result.updated_files:
        lines.append(f"    {f}")
    if result.skipped_files:
        lines.append(f"  skipped files   : {len(result.skipped_files)}")
        for f in result.skipped_files:
            lines.append(f"    {f}")
    lines.append("")
    lines.append(
        "Version bumped successfully." if result.ok else "Bump completed with errors."
    )
    lines.extend(next_steps(["Review the diff, run tests, commit, and tag the release."]))
    return "\n".join(lines)
