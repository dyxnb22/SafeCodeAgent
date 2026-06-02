"""Release preflight: aggregate local release gates into one fast check."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from safecode.core.diagnostic import Diagnostic
from safecode.release.check import ReleaseCheckResult, run_release_check
from safecode.release.docs_guard import DocsGuardResult, check_docs_finalized
from safecode.release.metadata import ReleaseMetadata, collect_release_metadata
from safecode.release.smoke import SmokeTestResult, run_smoke_tests
from safecode.release.ux import header, next_steps
from safecode.release.versions_governance import VersionsGovernanceResult, check_versions_governance


@dataclass(frozen=True)
class ReleasePreflightResult:
    """Aggregated result for the local release preflight."""

    release_check: ReleaseCheckResult
    smoke: SmokeTestResult
    metadata: ReleaseMetadata
    docs: DocsGuardResult
    versions_governance: VersionsGovernanceResult | None = None

    @property
    def ok(self) -> bool:
        governance_ok = self.versions_governance.ok if self.versions_governance is not None else True
        return (
            self.release_check.ok
            and self.smoke.ok
            and self.metadata.ok
            and self.docs.ok
            and governance_ok
        )

    def to_diagnostics(self) -> list[Diagnostic]:
        """Return one Diagnostic per top-level preflight component.

        These are coarse-grained component diagnostics. Use the underlying
        substrate's `to_diagnostics()` / `collect_smoke_diagnostics()` for
        finer breakdowns.
        """
        diagnostics: list[Diagnostic] = [
            Diagnostic.from_bool(
                "release_check",
                self.release_check.ok,
                "release check passed"
                if self.release_check.ok
                else self.release_check.tree_detail,
            ),
            Diagnostic.from_bool(
                "smoke",
                self.smoke.ok,
                "smoke passed"
                if self.smoke.ok
                else ", ".join(case.name for case in self.smoke.failed),
            ),
            Diagnostic.from_bool(
                "metadata",
                self.metadata.ok,
                "metadata ok" if self.metadata.ok else "; ".join(self.metadata.issues),
            ),
            Diagnostic.from_bool(
                "docs",
                self.docs.ok,
                "docs ok" if self.docs.ok else "; ".join(self.docs.issues),
            ),
        ]
        if self.versions_governance is not None:
            gov = self.versions_governance
            diagnostics.append(
                Diagnostic.from_bool(
                    "versions_governance",
                    gov.ok,
                    "governance ok" if gov.ok else "; ".join(gov.issues),
                )
            )
        return diagnostics


def run_release_preflight(
    project_root: Path | None = None,
    *,
    release_check_runner: Callable[[Path], ReleaseCheckResult] | None = None,
    smoke_runner: Callable[[], SmokeTestResult] | None = None,
    metadata_runner: Callable[[Path], ReleaseMetadata] | None = None,
    docs_runner: Callable[[str, Path], DocsGuardResult] | None = None,
    versions_governance_runner: Callable[[Path], VersionsGovernanceResult] | None = None,
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
    governance = (
        versions_governance_runner(root) if versions_governance_runner else check_versions_governance(root)
    )

    return ReleasePreflightResult(
        release_check=rc,
        smoke=smoke,
        metadata=metadata,
        docs=docs,
        versions_governance=governance,
    )


def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def render_release_preflight(result: ReleasePreflightResult) -> str:
    """Render a concise release preflight summary."""
    governance_ok = result.versions_governance.ok if result.versions_governance else True
    lines = header("SafeCode Release Preflight", result.ok) + [
        f"  [{_status(result.release_check.ok)}] release check",
        f"  [{_status(result.smoke.ok)}] smoke",
        f"  [{_status(result.metadata.ok)}] metadata",
        f"  [{_status(result.docs.ok)}] docs",
        f"  [{_status(governance_ok)}] versions governance",
        "",
    ]
    if result.ok:
        lines.append("Release preflight passed.")
        lines.extend(next_steps([], ok_message="Release is ready for publication."))
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
    if result.versions_governance and not result.versions_governance.ok:
        for issue in result.versions_governance.issues:
            lines.append(f"  versions governance: {issue}")
    lines.extend(next_steps(["Fix failed preflight checks, then rerun sac release preflight."]))
    return "\n".join(lines)
