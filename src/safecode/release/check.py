"""Release readiness check: reports version consistency and working-tree state."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from safecode.release.version_guard import VersionConsistencyResult, check_version_consistency


@dataclass(frozen=True)
class ReleaseCheckResult:
    """Structured result of a local release readiness check."""

    package_version: str
    runtime_version: str
    version_consistent: bool
    version_message: str
    tree_clean: bool | None  # None if git is unavailable
    tree_detail: str
    next_steps: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.version_consistent and (self.tree_clean is not False)


def _check_tree_clean(project_root: Path) -> tuple[bool | None, str]:
    """Return (clean, detail) for the git working tree at project_root."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=10,
        )
        if result.returncode != 0:
            return None, f"git exited {result.returncode}: {result.stderr.strip()}"
        output = result.stdout.strip()
        if output:
            lines = output.splitlines()
            return False, f"{len(lines)} uncommitted change(s)"
        return True, "working tree clean"
    except FileNotFoundError:
        return None, "git not found"
    except subprocess.TimeoutExpired:
        return None, "git timed out"


def run_release_check(
    project_root: Path | None = None,
    pyproject_path: Path | None = None,
    runtime_version: str | None = None,
) -> ReleaseCheckResult:
    """Run a local release readiness check and return a structured result.

    Args:
        project_root: directory to check for git status; defaults to cwd.
        pyproject_path: explicit pyproject.toml path; if None, auto-discovers.
        runtime_version: override runtime version (defaults to safecode.__version__).
    """
    root = project_root or Path.cwd()

    vc: VersionConsistencyResult = check_version_consistency(
        pyproject_path=pyproject_path,
        runtime_version=runtime_version,
    )

    tree_clean, tree_detail = _check_tree_clean(root)

    next_steps: list[str] = []
    if not vc.ok:
        next_steps.append(
            f"Update pyproject.toml or __version__ so both read {vc.package_version!r}."
        )
    if tree_clean is False:
        next_steps.append("Commit or stash pending changes before tagging.")
    if vc.ok and tree_clean is True:
        v = vc.package_version
        next_steps += [
            f'Run: PYTHONPATH=src python3 -m pytest -q',
            f'Then: git commit -m "Bump version to v{v}"',
            f'Then: git tag -a v{v} -m "v{v} <short summary>"',
        ]

    return ReleaseCheckResult(
        package_version=vc.package_version,
        runtime_version=vc.runtime_version,
        version_consistent=vc.ok,
        version_message=vc.message,
        tree_clean=tree_clean,
        tree_detail=tree_detail,
        next_steps=next_steps,
    )


def render_release_check(result: ReleaseCheckResult) -> str:
    """Render a ReleaseCheckResult as human-readable text."""
    lines: list[str] = [
        "SafeCode Release Check",
        "======================",
        f"  pyproject.toml version : {result.package_version}",
        f"  safecode.__version__   : {result.runtime_version}",
        f"  version consistent     : {'yes' if result.version_consistent else 'NO'}",
        f"  version detail         : {result.version_message}",
        f"  working tree           : {result.tree_detail}",
        "",
    ]
    if result.next_steps:
        lines.append("Next steps:")
        for step in result.next_steps:
            lines.append(f"  {step}")
    else:
        lines.append("All checks passed.")
    return "\n".join(lines)
