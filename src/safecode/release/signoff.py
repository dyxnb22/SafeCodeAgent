"""Final release signoff summary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from safecode.release.check import ReleaseCheckResult, run_release_check
from safecode.release.preflight import ReleasePreflightResult, run_release_preflight
from safecode.release.ux import header, next_steps


@dataclass(frozen=True)
class ReleaseSignoffResult:
    """Structured final signoff result."""

    version: str
    exact_tag: str | None
    release_check: ReleaseCheckResult
    preflight: ReleasePreflightResult

    @property
    def ok(self) -> bool:
        expected_tag = f"v{self.version}"
        return self.exact_tag == expected_tag and self.release_check.ok and self.preflight.ok


def run_release_signoff(project_root: Path | None = None) -> ReleaseSignoffResult:
    """Run final local signoff checks."""
    root = project_root or Path.cwd()
    release_check = run_release_check(root)
    preflight = run_release_preflight(root)
    exact_tag = release_check.tag_result.tag if release_check.tag_result else None
    return ReleaseSignoffResult(
        version=release_check.package_version,
        exact_tag=exact_tag,
        release_check=release_check,
        preflight=preflight,
    )


def render_release_signoff(result: ReleaseSignoffResult) -> str:
    """Render final signoff output."""
    lines = header("SafeCode Release Signoff", result.ok)
    lines.extend(
        [
            "  [deprecated] Use `sac release preflight` instead.",
            "  This command is kept for backward compatibility only.",
            "",
        ]
    )
    expected_tag = f"v{result.version}"
    lines.extend(
        [
            f"  package version : {result.version}",
            f"  exact tag       : {result.exact_tag or '(none)'}",
            f"  expected tag    : {expected_tag}",
            f"  release check   : {'PASS' if result.release_check.ok else 'FAIL'}",
            f"  preflight       : {'PASS' if result.preflight.ok else 'FAIL'}",
            "",
        ]
    )
    if result.ok:
        lines.append(f"Release signoff passed for v{result.version}.")
        lines.extend(next_steps([], ok_message="Release line is ready to close."))
    else:
        lines.append(f"Release signoff failed for v{result.version}.")
        lines.extend(next_steps(["Fix failed signoff checks, then rerun sac release signoff."]))
    return "\n".join(lines)
