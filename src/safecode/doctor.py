"""Environment checks for install and update polish."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from safecode import __version__
from safecode.core.diagnostic import Diagnostic, DiagnosticStatus

_PYPI_URL = "https://pypi.org/pypi/safecode/json"


def _fetch_latest_pypi_version(url: str = _PYPI_URL, *, timeout: int = 5) -> str | None:
    """Return the latest version string from PyPI, or None on any failure.

    Never raises. Sends no telemetry or identifying information beyond the
    standard HTTPS GET request User-Agent.
    """
    try:
        import json as _json
        from urllib.request import urlopen

        with urlopen(url, timeout=timeout) as resp:  # noqa: S310
            data = _json.loads(resp.read().decode("utf-8"))
            return data.get("info", {}).get("version")
    except Exception:
        return None


def _ver_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


@dataclass(frozen=True)
class DoctorCheck:
    """One doctor check (backward-compatible legacy shape)."""

    name: str
    passed: bool
    detail: str

    def to_diagnostic(self) -> Diagnostic:
        """Return the typed Diagnostic view of this check."""
        return Diagnostic.from_bool(self.name, self.passed, self.detail)


def _from_diagnostic(diagnostic: Diagnostic) -> DoctorCheck:
    """Render a Diagnostic as the legacy boolean DoctorCheck shape.

    SKIP and WARN both map to passed=False for the legacy view because the
    historical CLI surface uses a single passed bool. Internal callers should
    prefer `Doctor.run_diagnostics()` when they need PASS/FAIL/WARN/SKIP.
    """
    return DoctorCheck(
        name=diagnostic.name,
        passed=diagnostic.status is DiagnosticStatus.PASS,
        detail=diagnostic.message,
    )


class Doctor:
    """Check whether the local environment can run SafeCode."""

    def __init__(
        self,
        project_root: Path,
        *,
        fetch_latest_version: Callable[[], str | None] | None = None,
    ) -> None:
        self.project_root = project_root
        self._fetch_latest_version = fetch_latest_version or _fetch_latest_pypi_version

    def run_diagnostics(self, *, release: bool = False) -> list[Diagnostic]:
        """Return typed diagnostics (v2.8.x substrate)."""
        approval_dir = os.getenv("SAFECODE_APPROVAL_DIR")
        sandbox_dir = os.getenv("SAFECODE_SANDBOX_APPROVAL_DIR")
        diagnostics: list[Diagnostic] = [
            Diagnostic.from_bool(
                "python",
                sys.version_info >= (3, 11),
                sys.version.split()[0],
            ),
            Diagnostic.from_bool(
                "uv",
                shutil.which("uv") is not None,
                shutil.which("uv") or "not found",
            ),
            Diagnostic.from_bool(
                "project_root",
                self.project_root.exists(),
                str(self.project_root),
            ),
            Diagnostic.from_bool(
                "pyproject",
                (self.project_root / "pyproject.toml").exists(),
                "pyproject.toml",
            ),
            Diagnostic.from_bool(
                "config",
                (self.project_root / ".sac" / "config.toml").exists(),
                ".sac/config.toml",
            ),
            Diagnostic.from_bool(
                "sac_dir",
                (self.project_root / ".sac").exists(),
                ".sac",
            ),
            Diagnostic.from_bool(
                "approval_dir",
                bool(approval_dir),
                approval_dir or "not set",
            ),
            Diagnostic.from_bool(
                "sandbox_approval_dir",
                bool(sandbox_dir),
                sandbox_dir or "not set",
            ),
        ]
        diagnostics.append(self._last_session_cost_diagnostic())
        diagnostics.append(self._update_check_diagnostic())
        if release:
            diagnostics.extend(self.run_release_diagnostics())
        return diagnostics

    def _last_session_cost_diagnostic(self) -> "Diagnostic":
        """Return a PASS or SKIP diagnostic for the most recent session cost.json."""
        import glob
        pattern = str(self.project_root / ".sac" / "sessions" / "*" / "cost.json")
        cost_files = sorted(glob.glob(pattern))
        if not cost_files:
            return Diagnostic(
                name="last_session_cost",
                status=DiagnosticStatus.SKIP,
                message="no session cost data",
            )
        cost_file = cost_files[-1]
        try:
            import json as _json
            data = _json.loads(Path(cost_file).read_text(encoding="utf-8"))
            prompt = data.get("prompt_tokens", 0)
            completion = data.get("completion_tokens", 0)
            total = data.get("total_tokens", 0)
            msg = f"last_session: prompt={prompt} completion={completion} total={total}"
            return Diagnostic(name="last_session_cost", status=DiagnosticStatus.PASS, message=msg)
        except Exception:
            return Diagnostic(
                name="last_session_cost",
                status=DiagnosticStatus.SKIP,
                message="no session cost data",
            )

    def _update_check_diagnostic(self) -> Diagnostic:
        """Check PyPI for a newer version. Skips silently on network failure."""
        latest = self._fetch_latest_version()
        if latest is None:
            return Diagnostic(
                name="update_check",
                status=DiagnosticStatus.SKIP,
                message="update check skipped (offline or network unavailable)",
            )
        if _ver_tuple(latest) > _ver_tuple(__version__):
            return Diagnostic(
                name="update_check",
                status=DiagnosticStatus.WARN,
                message=f"update available: {__version__} → {latest}",
            )
        return Diagnostic(
            name="update_check",
            status=DiagnosticStatus.PASS,
            message=f"up to date ({__version__})",
        )

    def run(self, *, release: bool = False) -> list[DoctorCheck]:
        """Run environment checks, optionally including release diagnostics.

        Preserves the legacy DoctorCheck list shape used by `sac doctor`.
        """
        return [_from_diagnostic(d) for d in self.run_diagnostics(release=release)]

    def run_release_diagnostics(self) -> list[Diagnostic]:
        """Run release diagnostics without mutating the checkout."""
        from safecode.release.docs_guard import check_docs_finalized
        from safecode.release.preflight import run_release_preflight
        from safecode.release.version_guard import (
            check_tag_consistency,
            check_version_consistency,
        )

        version = check_version_consistency(
            pyproject_path=self.project_root / "pyproject.toml",
            runtime_version=__version__,
        )
        tag = check_tag_consistency(version.package_version, project_root=self.project_root)
        docs = check_docs_finalized(__version__, project_root=self.project_root)
        preflight = run_release_preflight(self.project_root)

        return [
            Diagnostic.from_bool("release_version", version.ok, version.message),
            Diagnostic.from_bool("release_tag", tag.consistent, tag.message),
            Diagnostic.from_bool(
                "release_docs",
                docs.ok,
                "docs finalized" if docs.ok else "; ".join(docs.issues),
            ),
            Diagnostic.from_bool(
                "release_preflight",
                preflight.ok,
                "preflight passed" if preflight.ok else "preflight needs attention",
            ),
        ]

    def run_release(self) -> list[DoctorCheck]:
        """Return release diagnostics in the legacy DoctorCheck shape."""
        return [_from_diagnostic(d) for d in self.run_release_diagnostics()]
