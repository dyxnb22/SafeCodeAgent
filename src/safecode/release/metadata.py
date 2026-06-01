"""Release metadata index: collects version, tag, notes, and baseline consistency."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ReleaseMetadata:
    """Aggregated local release metadata snapshot."""

    package_version: str
    runtime_version: str
    latest_git_tag: str | None
    version_note_files: list[str]
    has_version_note: bool
    skill_mentions_version: bool
    issues: list[str]

    @property
    def ok(self) -> bool:
        return len(self.issues) == 0


def _get_latest_git_tag(project_root: Path) -> str | None:
    """Return the most recent v* tag reachable from HEAD, or None."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0", "--match", "v*"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _list_version_notes(version_notes_dir: Path) -> list[str]:
    """Return sorted list of version-note filenames in *version_notes_dir*."""
    if not version_notes_dir.is_dir():
        return []
    return sorted(p.name for p in version_notes_dir.iterdir() if p.suffix == ".md")


def _note_exists_for_version(version: str, note_files: list[str]) -> bool:
    prefix = f"v{version}-"
    return any(name.startswith(prefix) for name in note_files)


def _skill_mentions_version(skill_path: Path, version: str) -> bool:
    if not skill_path.is_file():
        return False
    try:
        text = skill_path.read_text(encoding="utf-8")
        return version in text
    except OSError:
        return False


_UNSET = object()  # sentinel: auto-detect from git


def collect_release_metadata(
    project_root: Path | None = None,
    *,
    runtime_version: str | None = None,
    package_version: str | None = None,
    latest_git_tag: str | None | object = _UNSET,  # type: ignore[assignment]
    version_notes_dir: Path | None = None,
    skill_path: Path | None = None,
) -> ReleaseMetadata:
    """Collect local release metadata for auditing.

    All path/version arguments accept injected values for testing.
    """
    root = project_root or Path.cwd()

    import safecode

    rv = runtime_version if runtime_version is not None else safecode.__version__

    if package_version is None:
        try:
            import tomllib
            _find = root / "pyproject.toml"
            if _find.is_file():
                with open(_find, "rb") as fh:
                    package_version = tomllib.load(fh)["project"]["version"]
            else:
                package_version = "<not found>"
        except Exception:  # noqa: BLE001
            package_version = "<read error>"

    if latest_git_tag is _UNSET:
        latest_git_tag = _get_latest_git_tag(root)

    notes_dir = version_notes_dir or (root / "docs" / "version-notes")
    note_files = _list_version_notes(notes_dir)
    has_note = _note_exists_for_version(package_version, note_files)

    sk_path = skill_path or (root / ".claude" / "skills" / "current" / "SKILL.md")
    skill_ok = _skill_mentions_version(sk_path, package_version)

    issues: list[str] = []
    if not has_note:
        issues.append(
            f"No version-note file found for v{package_version} in {notes_dir}."
        )
    if not skill_ok:
        issues.append(
            f".claude/skills/current/SKILL.md does not mention version {package_version}."
        )

    return ReleaseMetadata(
        package_version=package_version,
        runtime_version=rv,
        latest_git_tag=latest_git_tag,
        version_note_files=note_files,
        has_version_note=has_note,
        skill_mentions_version=skill_ok,
        issues=issues,
    )


def render_release_metadata(meta: ReleaseMetadata) -> str:
    """Render ReleaseMetadata as human-readable text."""
    lines = [
        "SafeCode Release Metadata",
        "=========================",
        f"  package version        : {meta.package_version}",
        f"  runtime version        : {meta.runtime_version}",
        f"  latest git tag         : {meta.latest_git_tag or '(none)'}",
        f"  version-note present   : {'yes' if meta.has_version_note else 'NO'}",
        f"  SKILL.md mentions ver  : {'yes' if meta.skill_mentions_version else 'NO'}",
        f"  version-note count     : {len(meta.version_note_files)}",
        "",
    ]
    if meta.issues:
        lines.append("Issues:")
        for issue in meta.issues:
            lines.append(f"  {issue}")
    else:
        lines.append("Metadata index looks good.")
    return "\n".join(lines)
