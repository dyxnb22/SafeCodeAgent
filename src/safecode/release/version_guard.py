"""Version consistency guard: verifies pyproject.toml matches safecode.__version__."""

from __future__ import annotations

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
