"""Version consistency guard: verifies pyproject.toml matches safecode.__version__."""

from __future__ import annotations

import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VersionConsistencyResult:
    """Result of a version consistency check."""

    ok: bool
    package_version: str
    runtime_version: str
    message: str


def _find_pyproject(start: Path) -> Path | None:
    """Walk up from *start* looking for pyproject.toml."""
    for candidate in [start, *start.parents]:
        p = candidate / "pyproject.toml"
        if p.is_file():
            return p
    return None


def check_version_consistency(
    pyproject_path: Path | None = None,
    runtime_version: str | None = None,
) -> VersionConsistencyResult:
    """Return a VersionConsistencyResult comparing pyproject.toml to safecode.__version__.

    Args:
        pyproject_path: explicit path to pyproject.toml; if None, searches upward
                        from the safecode package directory.
        runtime_version: override the runtime version (defaults to safecode.__version__).
    """
    import safecode

    rv = runtime_version if runtime_version is not None else safecode.__version__

    if pyproject_path is None:
        pkg_dir = Path(safecode.__file__).parent
        pyproject_path = _find_pyproject(pkg_dir)

    if pyproject_path is None or not pyproject_path.is_file():
        searched = str(pyproject_path) if pyproject_path else "not found"
        return VersionConsistencyResult(
            ok=False,
            package_version="<not found>",
            runtime_version=rv,
            message=(
                f"pyproject.toml not found (searched: {searched}). "
                "Run this check from the project root."
            ),
        )

    try:
        with open(pyproject_path, "rb") as fh:
            data = tomllib.load(fh)
        pv = data["project"]["version"]
    except (KeyError, OSError, tomllib.TOMLDecodeError) as exc:
        return VersionConsistencyResult(
            ok=False,
            package_version="<read error>",
            runtime_version=rv,
            message=f"Could not read version from {pyproject_path}: {exc}",
        )

    if pv == rv:
        return VersionConsistencyResult(
            ok=True,
            package_version=pv,
            runtime_version=rv,
            message=f"OK — both versions are {pv}",
        )

    return VersionConsistencyResult(
        ok=False,
        package_version=pv,
        runtime_version=rv,
        message=(
            f"Version mismatch: pyproject.toml says {pv!r} "
            f"but safecode.__version__ is {rv!r}. "
            f"Update one to match the other before tagging."
        ),
    )


# ---------------------------------------------------------------------------
# Tag consistency
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TagConsistencyResult:
    """Result of a git-tag vs package-version consistency check."""

    tag: str | None
    """The exact git tag at HEAD, or None if not at an exact tag."""

    tag_available: bool
    """True if HEAD is at an exact annotated/lightweight tag."""

    consistent: bool
    """True only when tag_available and the tag matches the package version."""

    package_version: str
    message: str


def get_exact_git_tag(project_root: Path) -> str | None:
    """Return the exact git tag at HEAD, or None if none / git unavailable."""
    try:
        result = subprocess.run(
            ["git", "describe", "--exact-match", "--tags", "HEAD"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


_TAG_AUTO = object()  # sentinel: auto-detect tag from git


def check_tag_consistency(
    package_version: str,
    *,
    tag: str | None | object = _TAG_AUTO,
    project_root: Path | None = None,
) -> TagConsistencyResult:
    """Check whether the git tag at HEAD matches the package version.

    Args:
        package_version: expected version string (e.g. "2.6.6").
        tag: explicit tag string, None (no exact tag), or _TAG_AUTO to detect via git.
        project_root: directory for git detection when tag is _TAG_AUTO; defaults to cwd.
    """
    if tag is _TAG_AUTO:
        root = project_root or Path.cwd()
        tag = get_exact_git_tag(root)

    expected_tag = f"v{package_version}"

    if tag is None:
        return TagConsistencyResult(
            tag=None,
            tag_available=False,
            consistent=False,
            package_version=package_version,
            message=(
                f"No exact git tag at HEAD — cannot confirm tag matches "
                f"package version {package_version!r}. "
                f"Tag with: git tag -a {expected_tag} -m '{expected_tag} <summary>'"
            ),
        )

    if tag == expected_tag:
        return TagConsistencyResult(
            tag=tag,
            tag_available=True,
            consistent=True,
            package_version=package_version,
            message=f"OK — tag {tag!r} matches package version {package_version!r}",
        )

    return TagConsistencyResult(
        tag=tag,
        tag_available=True,
        consistent=False,
        package_version=package_version,
        message=(
            f"Tag mismatch: git tag is {tag!r} but package version is "
            f"{package_version!r} (expected tag {expected_tag!r})."
        ),
    )
