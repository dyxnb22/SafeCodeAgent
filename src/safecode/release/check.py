"""Release readiness check: reports version consistency and working-tree state."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from safecode.release.version_guard import (
    TagConsistencyResult,
    VersionConsistencyResult,
    _TAG_AUTO,
    check_tag_consistency,
    check_version_consistency,
)
from safecode.release.ux import header, next_steps


@dataclass(frozen=True)
class ReleaseCheckResult:
    """Structured result of a local release readiness check."""

    package_version: str
    runtime_version: str
    version_consistent: bool
    version_message: str
    tree_clean: bool | None  # None if git is unavailable
    tree_detail: str
    tag_result: TagConsistencyResult | None = None
    next_steps: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        tag_ok = self.tag_result is None or self.tag_result.consistent
        return self.version_consistent and (self.tree_clean is not False) and tag_ok


_UNSET = object()  # sentinel for auto-detecting git tag


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
    git_tag: str | None = _UNSET,  # type: ignore[assignment]
) -> ReleaseCheckResult:
    """Run a local release readiness check and return a structured result.

    Args:
        project_root: directory to check for git status; defaults to cwd.
        pyproject_path: explicit pyproject.toml path; if None, auto-discovers.
        runtime_version: override runtime version (defaults to safecode.__version__).
        git_tag: explicit tag string for testing; sentinel _UNSET means auto-detect.
    """
    root = project_root or Path.cwd()

    vc: VersionConsistencyResult = check_version_consistency(
        pyproject_path=pyproject_path,
        runtime_version=runtime_version,
    )

    tree_clean, tree_detail = _check_tree_clean(root)

    # Tag consistency — only run when package version is readable.
    # git_tag=_UNSET → auto-detect; git_tag=None → no tag; git_tag="v..." → explicit.
    if vc.package_version not in ("<not found>", "<read error>"):
        if git_tag is _UNSET:  # type: ignore[comparison-overlap]
            tag_arg = _TAG_AUTO  # let check_tag_consistency detect via git
        else:
            tag_arg = git_tag  # explicit value (str or None)
        tag_result: TagConsistencyResult | None = check_tag_consistency(
            vc.package_version,
            tag=tag_arg,
            project_root=root,
        )
    else:
        tag_result = None

    next_steps: list[str] = []
    if not vc.ok:
        next_steps.append(
            f"Update pyproject.toml or __version__ so both read {vc.package_version!r}."
        )
    if tree_clean is False:
        next_steps.append("Commit or stash pending changes before tagging.")
    if vc.ok and tree_clean is True:
        v = vc.package_version
        if tag_result is not None and tag_result.consistent:
            pass  # already correctly tagged — no further action needed
        elif tag_result is not None and not tag_result.tag_available:
            next_steps.append(
                f'git tag -a v{v} -m "v{v} <short summary>"'
            )
        elif tag_result is not None and not tag_result.consistent:
            next_steps.append(
                f"Tag mismatch: current tag is {tag_result.tag!r}; "
                f"expected v{v}. Re-tag or fix the version."
            )

    return ReleaseCheckResult(
        package_version=vc.package_version,
        runtime_version=vc.runtime_version,
        version_consistent=vc.ok,
        version_message=vc.message,
        tree_clean=tree_clean,
        tree_detail=tree_detail,
        tag_result=tag_result,
        next_steps=next_steps,
    )


def _summarise_state(result: ReleaseCheckResult) -> str:
    """Return a one-line summary of the overall release state."""
    if (
        result.version_consistent
        and result.tree_clean is True
        and result.tag_result is not None
        and result.tag_result.consistent
    ):
        return "Ready to release — versions match, tree is clean, and tag is correct."
    if result.tree_clean is None:
        return (
            "Version consistent; working-tree and tag state unknown "
            "(git unavailable — run from a git checkout)."
        )
    return "One or more checks need attention — see next steps above."


def render_release_check(result: ReleaseCheckResult) -> str:
    """Render a ReleaseCheckResult as human-readable text."""
    lines: list[str] = header("SafeCode Release Check", result.ok) + [
        f"  pyproject.toml version : {result.package_version}",
        f"  safecode.__version__   : {result.runtime_version}",
        f"  version consistent     : {'yes' if result.version_consistent else 'NO'}",
        f"  version detail         : {result.version_message}",
        f"  working tree           : {result.tree_detail}",
    ]
    if result.tag_result is not None:
        tr = result.tag_result
        tag_label = tr.tag if tr.tag else "(none)"
        tag_ok = "yes" if tr.consistent else ("no exact tag" if not tr.tag_available else "NO")
        lines.append(f"  git tag at HEAD        : {tag_label}")
        lines.append(f"  tag consistent         : {tag_ok}")
        lines.append(f"  tag detail             : {tr.message}")
    lines.append("")
    lines.append("")
    lines.extend(next_steps(result.next_steps, ok_message="Release check is ready."))
    lines.append("")
    lines.append(_summarise_state(result))
    return "\n".join(lines)
