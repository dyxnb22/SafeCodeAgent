"""Release docs finalization guard: verifies human-facing docs are updated for the release."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


RELEASE_COMMANDS: tuple[str, ...] = (
    "sac release bump",
    "sac release check",
    "sac release smoke",
    "sac release meta",
    "sac release preflight",
)

_README_CANDIDATES = ("README.md", "README.rst", "README.txt")
_INSTALL_CANDIDATES = ("docs/install-update.md", "docs/install-update.rst")


@dataclass(frozen=True)
class DocsGuardResult:
    """Result of a release docs finalization check."""

    has_version_note: bool
    skill_mentions_version: bool
    release_commands_documented: bool
    issues: list[str]

    @property
    def ok(self) -> bool:
        return len(self.issues) == 0


def _note_exists(version: str, notes_dir: Path) -> bool:
    if not notes_dir.is_dir():
        return False
    prefix = f"v{version}-"
    return any(p.name.startswith(prefix) for p in notes_dir.iterdir() if p.suffix == ".md")


def _ledger_entry_exists(version: str, ledger_path: Path) -> bool:
    if not ledger_path.is_file():
        return False
    pattern = re.compile(rf"^##\s+v{re.escape(version)}(?:\s|[-:]|$)")
    try:
        return any(pattern.match(line.strip()) for line in ledger_path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return False


def _skill_mentions(version: str, skill_path: Path) -> bool:
    if not skill_path.is_file():
        return False
    try:
        return version in skill_path.read_text(encoding="utf-8")
    except OSError:
        return False


def _docs_mention_release_commands(project_root: Path) -> bool:
    """Return True if README or docs/install-update mentions at least one release command."""
    candidates = [project_root / c for c in _README_CANDIDATES + _INSTALL_CANDIDATES]
    for path in candidates:
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
                if any(cmd in text for cmd in RELEASE_COMMANDS):
                    return True
            except OSError:
                pass
    return False


def check_docs_finalized(
    version: str,
    *,
    project_root: Path | None = None,
    notes_dir: Path | None = None,
    release_ledger_path: Path | None = None,
    skill_path: Path | None = None,
    release_commands_documented: bool | None = None,
) -> DocsGuardResult:
    """Check that human-facing docs are updated for *version*.

    Args:
        version: package version string, e.g. "2.6.9".
        project_root: repo root; defaults to cwd.
        notes_dir: legacy path to version-notes directory; used only as a fallback.
        release_ledger_path: path to release ledger; defaults to project_root/docs/release-ledger.md.
        skill_path: path to SKILL.md; defaults to project_root/.agents/skills/current/SKILL.md.
        release_commands_documented: inject True/False for testing; if None, auto-detects.
    """
    root = project_root or Path.cwd()
    nd = notes_dir or (root / "docs" / "version-notes")
    ledger = release_ledger_path or (root / "docs" / "release-ledger.md")
    sp = skill_path or (root / ".agents" / "skills" / "current" / "SKILL.md")

    if release_ledger_path is not None:
        has_note = _ledger_entry_exists(version, ledger)
    elif notes_dir is not None:
        has_note = _note_exists(version, nd)
    else:
        has_note = _ledger_entry_exists(version, ledger) or _note_exists(version, nd)
    skill_ok = _skill_mentions(version, sp)

    if release_commands_documented is None:
        cmds_ok = _docs_mention_release_commands(root)
    else:
        cmds_ok = release_commands_documented

    issues: list[str] = []
    if not has_note:
        issues.append(
            f"No release ledger entry found for v{version} in {ledger}. "
            f"Add a `## v{version}` entry to docs/release-ledger.md."
        )
    if not cmds_ok:
        issues.append(
            "README.md or docs/install-update.md does not mention any release command "
            f"({', '.join(RELEASE_COMMANDS)}). Update the docs."
        )

    return DocsGuardResult(
        has_version_note=has_note,
        skill_mentions_version=skill_ok,
        release_commands_documented=cmds_ok,
        issues=issues,
    )
