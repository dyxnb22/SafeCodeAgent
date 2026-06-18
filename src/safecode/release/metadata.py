"""Release metadata index: collects version, tag, ledger, and baseline consistency."""

from __future__ import annotations

import subprocess
import re
from dataclasses import dataclass, field
from pathlib import Path

from safecode.release.ux import header, next_steps


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
    version_note_heading_ok: bool = True
    duplicate_version_note_files: list[str] = field(default_factory=list)

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
    return sorted(
        p.name
        for p in version_notes_dir.iterdir()
        if p.suffix == ".md" and p.name.startswith("v")
    )


def _note_exists_for_version(version: str, note_files: list[str]) -> bool:
    prefix = f"v{version}-"
    return any(name.startswith(prefix) for name in note_files)


def _notes_for_version(version: str, note_files: list[str]) -> list[str]:
    prefix = f"v{version}-"
    return [name for name in note_files if name.startswith(prefix)]


def _ledger_has_version(version: str, ledger_path: Path) -> bool:
    if not ledger_path.is_file():
        return False
    pattern = re.compile(rf"^##\s+v{re.escape(version)}(?:\s|[-:]|$)")
    try:
        return any(pattern.match(line.strip()) for line in ledger_path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return False


def _first_heading_mentions_version(note_path: Path, version: str) -> bool:
    try:
        for line in note_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return f"v{version}" in stripped
        return False
    except OSError:
        return False


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
    release_ledger_path: Path | None = None,
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
    ledger_path = release_ledger_path or (root / "docs" / "release-ledger.md")
    has_ledger_entry = _ledger_has_version(package_version, ledger_path)
    has_note = has_ledger_entry or _note_exists_for_version(package_version, note_files)
    matching_notes = _notes_for_version(package_version, note_files)
    duplicate_notes = matching_notes[1:] if len(matching_notes) > 1 else []
    heading_ok = True
    if not has_ledger_entry and matching_notes:
        heading_ok = _first_heading_mentions_version(
            notes_dir / matching_notes[0],
            package_version,
        )

    sk_path = skill_path or (root / ".claude" / "skills" / "current" / "SKILL.md")
    skill_ok = _skill_mentions_version(sk_path, package_version)

    issues: list[str] = []
    if not has_note:
        issues.append(
            f"No release ledger entry found for v{package_version} in {ledger_path}."
        )
    elif not heading_ok:
        issues.append(
            f"Version-note heading for v{package_version} does not mention v{package_version}."
        )
    if duplicate_notes and not has_ledger_entry:
        issues.append(
            f"Duplicate version-note files found for v{package_version}: "
            f"{', '.join(matching_notes)}."
        )

    return ReleaseMetadata(
        package_version=package_version,
        runtime_version=rv,
        latest_git_tag=latest_git_tag,
        version_note_files=note_files,
        has_version_note=has_note,
        skill_mentions_version=skill_ok,
        issues=issues,
        version_note_heading_ok=heading_ok,
        duplicate_version_note_files=duplicate_notes,
    )


def render_release_metadata(meta: ReleaseMetadata) -> str:
    """Render ReleaseMetadata as human-readable text."""
    lines = header("SafeCode Release Metadata", meta.ok) + [
        f"  package version        : {meta.package_version}",
        f"  runtime version        : {meta.runtime_version}",
        f"  latest git tag         : {meta.latest_git_tag or '(none)'}",
        f"  release entry present  : {'yes' if meta.has_version_note else 'NO'}",
        f"  legacy note heading    : {'yes' if meta.version_note_heading_ok else 'NO'}",
        f"  duplicate legacy notes : {len(meta.duplicate_version_note_files)}",
        f"  SKILL.md mentions ver  : {'yes' if meta.skill_mentions_version else 'no'}",
        f"  legacy note count      : {len(meta.version_note_files)}",
        "",
    ]
    if meta.issues:
        lines.append("Issues:")
        for issue in meta.issues:
            lines.append(f"  {issue}")
        lines.extend(next_steps(["Fix metadata issues, then rerun sac release meta."]))
    else:
        lines.append("Metadata index looks good.")
        lines.extend(next_steps([], ok_message="Metadata is ready."))
    return "\n".join(lines)
