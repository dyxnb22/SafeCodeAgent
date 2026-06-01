"""Release preflight: aggregate local release gates into one fast check."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from safecode.release.check import ReleaseCheckResult, run_release_check
from safecode.release.docs_guard import DocsGuardResult, check_docs_finalized
from safecode.release.metadata import ReleaseMetadata, collect_release_metadata
from safecode.release.smoke import SmokeTestResult, run_smoke_tests


@dataclass(frozen=True)
class ReleasePreflightResult:
    """Aggregated result for the local release preflight."""

    release_check: ReleaseCheckResult
    smoke: SmokeTestResult
    metadata: ReleaseMetadata
    docs: DocsGuardResult

    @property
    def ok(self) -> bool:
        return (
            self.release_check.ok
            and self.smoke.ok
            and self.metadata.ok
            and self.docs.ok
        )


def run_release_preflight(
    project_root: Path | None = None,
    *,
    release_check_runner: Callable[[Path], ReleaseCheckResult] | None = None,
    smoke_runner: Callable[[], SmokeTestResult] | None = None,
    metadata_runner: Callable[[Path], ReleaseMetadata] | None = None,
    docs_runner: Callable[[str, Path], DocsGuardResult] | None = None,
) -> ReleasePreflightResult:
    """Run fast local release checks and return a structured aggregate result."""
    root = project_root or Path.cwd()

    rc = release_check_runner(root) if release_check_runner else run_release_check(root)
    smoke = smoke_runner() if smoke_runner else run_smoke_tests()
    metadata = metadata_runner(root) if metadata_runner else collect_release_metadata(root)
    if docs_runner:
        docs = docs_runner(metadata.package_version, root)
    else:
        docs = check_docs_finalized(metadata.package_version, project_root=root)

    return ReleasePreflightResult(
        release_check=rc,
        smoke=smoke,
        metadata=metadata,
        docs=docs,
    )


def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def render_release_preflight(result: ReleasePreflightResult) -> str:
    """Render a concise release preflight summary."""
    lines = [
        "SafeCode Release Preflight",
        "==========================",
        f"  [{_status(result.release_check.ok)}] release check",
        f"  [{_status(result.smoke.ok)}] smoke",
        f"  [{_status(result.metadata.ok)}] metadata",
        f"  [{_status(result.docs.ok)}] docs",
        "",
    ]
    if result.ok:
        lines.append("Release preflight passed.")
        return "\n".join(lines)

    lines.append("Failures:")
    if not result.release_check.ok:
        lines.append(f"  release check: {result.release_check.tree_detail}")
        if result.release_check.next_steps:
            for step in result.release_check.next_steps:
                lines.append(f"    next: {step}")
    if not result.smoke.ok:
        failed = ", ".join(case.name for case in result.smoke.failed)
        lines.append(f"  smoke: {failed}")
    if not result.metadata.ok:
        for issue in result.metadata.issues:
            lines.append(f"  metadata: {issue}")
    if not result.docs.ok:
        for issue in result.docs.issues:
            lines.append(f"  docs: {issue}")
    return "\n".join(lines)
