"""Generate Markdown changelogs from local version-note files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from safecode.release.ux import header, next_steps

_NOTE_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)-.*\.md$")


@dataclass(frozen=True)
class ChangelogEntry:
    """One version-note entry included in a changelog."""

    version: str
    filename: str
    heading: str
    summary: str


@dataclass(frozen=True)
class ChangelogResult:
    """Structured changelog generation result."""

    from_version: str
    to_version: str
    entries: list[ChangelogEntry]
    issues: list[str]

    @property
    def ok(self) -> bool:
        return not self.issues


def _version_tuple(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Invalid version {version!r}; expected X.Y.Z.")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def _first_heading_and_summary(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    heading = path.stem
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            break
    summary_lines: list[str] = []
    in_summary = False
    for line in lines:
        stripped = line.strip()
        if stripped.lower() == "## summary":
            in_summary = True
            continue
        if in_summary and stripped.startswith("## "):
            break
        if in_summary and stripped:
            summary_lines.append(stripped)
    summary = " ".join(summary_lines) if summary_lines else heading
    return heading, summary


def generate_changelog(
    from_version: str,
    to_version: str,
    *,
    version_notes_dir: Path | None = None,
) -> ChangelogResult:
    """Generate changelog entries between inclusive semantic version bounds."""
    issues: list[str] = []
    try:
        low = _version_tuple(from_version)
        high = _version_tuple(to_version)
    except ValueError as exc:
        return ChangelogResult(from_version, to_version, [], [str(exc)])

    if low > high:
        return ChangelogResult(
            from_version,
            to_version,
            [],
            [f"from version {from_version!r} must be <= to version {to_version!r}."],
        )

    notes_dir = version_notes_dir or Path("docs") / "version-notes"
    if not notes_dir.is_dir():
        return ChangelogResult(
            from_version,
            to_version,
            [],
            [f"Version-notes directory not found: {notes_dir}."],
        )

    entries: list[ChangelogEntry] = []
    for path in sorted(notes_dir.iterdir()):
        match = _NOTE_RE.match(path.name)
        if not match:
            continue
        version = match.group("version")
        vt = _version_tuple(version)
        if low <= vt <= high:
            heading, summary = _first_heading_and_summary(path)
            entries.append(
                ChangelogEntry(
                    version=version,
                    filename=path.name,
                    heading=heading,
                    summary=summary,
                )
            )

    entries.sort(key=lambda entry: _version_tuple(entry.version))
    if not entries:
        issues.append(f"No version notes found from v{from_version} to v{to_version}.")

    return ChangelogResult(from_version, to_version, entries, issues)


def render_changelog(result: ChangelogResult) -> str:
    """Render a changelog result as Markdown."""
    lines = header("SafeCode Release Changelog", result.ok)
    lines.append(f"# Changelog v{result.from_version}..v{result.to_version}")
    lines.append("")
    if result.entries:
        for entry in result.entries:
            lines.append(f"## v{entry.version}")
            lines.append("")
            lines.append(f"- {entry.summary}")
            lines.append(f"- Source: `docs/version-notes/{entry.filename}`")
            lines.append("")
    if result.issues:
        lines.append("Issues:")
        for issue in result.issues:
            lines.append(f"- {issue}")
        lines.extend(next_steps(["Fix changelog inputs, then rerun sac release changelog."]))
    else:
        lines.extend(next_steps([], ok_message="Changelog generated; no files were changed."))
    return "\n".join(lines)
